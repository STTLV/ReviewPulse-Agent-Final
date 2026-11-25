"""Rutas HTTP de ReviewPulse."""
from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from starlette.requests import ClientDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..agente.bucle import ManejadorAgente, resolver
from ..agente.traza import Traza
from ..ciclo.cierre import ManejadorDeterminista
from .estado import EstadoAPI

_LOG = logging.getLogger(__name__)


class SolicitudChat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mensaje: str = Field(min_length=1, max_length=2000)

    @field_validator("mensaje")
    @classmethod
    def mensaje_no_vacio(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("El mensaje no puede estar vacío.")
        return valor


class SolicitudCierre(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semana: int = Field(ge=0, strict=True)


def _filtrar_evento_sse(estado: EstadoAPI, valor: object) -> object:
    if isinstance(valor, str):
        return estado.texto_seguro(valor)
    if isinstance(valor, dict):
        return {
            (
                estado.texto_seguro(clave)
                if isinstance(clave, str)
                else clave
            ): _filtrar_evento_sse(estado, elemento)
            for clave, elemento in valor.items()
        }
    if isinstance(valor, (list, tuple)):
        return [_filtrar_evento_sse(estado, elemento) for elemento in valor]
    if isinstance(valor, (int, float, bool)) or valor is None:
        return valor
    return estado.texto_seguro(str(valor))


def _evento(nombre: str, datos: dict, estado: EstadoAPI) -> str:
    contenido = json.dumps(
        _filtrar_evento_sse(estado, datos), ensure_ascii=False
    )
    return f"event: {nombre}\ndata: {contenido}\n\n"


def _autorizar(estado: EstadoAPI, codigo: str | None) -> None:
    if not estado.autorizado(codigo):
        raise HTTPException(status_code=401, detail="Código de acceso inválido.")


def _ocupado(estado: EstadoAPI) -> None:
    if not estado.candado.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="ocupado")


class _RespuestaSSEProtegida(StreamingResponse):
    def __init__(
        self,
        contenido,
        estado: EstadoAPI,
        trabajador_iniciado: threading.Event,
        cancel_event: threading.Event,
        headers: dict[str, str] | None = None,
    ):
        self._estado = estado
        self._trabajador_iniciado = trabajador_iniciado
        self._cancel_event = cancel_event
        super().__init__(
            contenido, media_type="text/event-stream", headers=headers
        )

    async def __call__(self, scope, receive, send):
        try:
            _ocupado(self._estado)
        except HTTPException as exc:
            respuesta = JSONResponse(
                {"detail": exc.detail}, status_code=exc.status_code
            )
            await respuesta(scope, receive, send)
            return

        try:
            await super().__call__(scope, receive, send)
        except (ClientDisconnect, asyncio.CancelledError, GeneratorExit):
            self._cancel_event.set()
            raise
        except BaseException:
            self._cancel_event.set()
            raise
        finally:
            if not self._trabajador_iniciado.is_set():
                self._estado.candado.release()

    async def listen_for_disconnect(self, receive):
        try:
            await super().listen_for_disconnect(receive)
        finally:
            self._cancel_event.set()


def crear_router(estado: EstadoAPI) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/salud")
    def salud() -> dict:
        return {"estado": "ok"}

    @router.post("/chat")
    def chat(
        solicitud: SolicitudChat,
        codigo: str | None = Header(default=None, alias="X-Codigo-Acceso"),
    ) -> StreamingResponse:
        _autorizar(estado, codigo)
        trabajador_iniciado = threading.Event()
        cancel_event = threading.Event()
        timeout_s = estado.ajustes.api_chat_timeout_s

        def transmitir():
            if estado.presupuesto_agotado():
                yield from emitir_traza_demo()
                return

            deadline = time.monotonic() + timeout_s
            eventos: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=64)

            def publicar(tipo: str, valor: object) -> None:
                while not cancel_event.is_set():
                    if time.monotonic() >= deadline:
                        cancel_event.set()
                        return
                    try:
                        eventos.put((tipo, valor), timeout=0.05)
                        return
                    except queue.Full:
                        continue

            def emitir_paso(evento: dict) -> None:
                if cancel_event.is_set() or time.monotonic() >= deadline:
                    cancel_event.set()
                    return
                estado.agregar_evento(evento)
                publicar("paso", evento)

            def ejecutar_agente() -> None:
                try:
                    resultado = resolver(
                        solicitud.mensaje,
                        estado.llm,
                        estado.contexto(),
                        traza=Traza(),
                        al_evento=emitir_paso,
                        cancel_event=cancel_event,
                        deadline=deadline,
                    )
                    publicar("resultado", resultado)
                except Exception as exc:
                    _LOG.error("Fallo interno del agente API: %s", type(exc).__name__)
                    publicar("fallo", None)
                finally:
                    estado.candado.release()

            trabajador = threading.Thread(target=ejecutar_agente, daemon=True)
            trabajador_iniciado.set()
            try:
                trabajador.start()
            except BaseException:
                trabajador_iniciado.clear()
                raise
            while True:
                restante = deadline - time.monotonic()
                if restante <= 0:
                    cancel_event.set()
                    yield _evento("error", {
                        "error": "limite_tiempo",
                        "mensaje": f"La solicitud superó el límite de {timeout_s:g} segundos.",
                    }, estado)
                    return
                if cancel_event.is_set():
                    return
                try:
                    tipo, valor = eventos.get(timeout=min(0.1, restante))
                except queue.Empty:
                    continue
                if tipo == "paso":
                    yield _evento("paso", {"traza": valor}, estado)
                    continue
                if tipo == "resultado":
                    resultado = valor
                    if resultado.ok:
                        yield _evento("final", {
                            "texto": estado.texto_seguro(resultado.texto),
                            "modo_demo": False,
                            "motivo": resultado.motivo,
                        }, estado)
                    elif estado.presupuesto_agotado():
                        yield from emitir_traza_demo()
                    else:
                        yield _evento("error", {
                            "error": resultado.motivo,
                            "mensaje": estado.texto_seguro(resultado.texto),
                        }, estado)
                    break
                yield _evento("error", {
                    "error": "error_interno",
                    "mensaje": "No fue posible completar la solicitud.",
                }, estado)
                break

        def emitir_traza_demo():
            traza = estado.siguiente_traza_demo(solicitud.mensaje)
            if not traza.get("coincidencia_demo", False):
                # Una pregunta ajena a las grabaciones NO debe provocar una
                # respuesta o traza de otra consulta, aunque haya un fallback.
                aviso = (
                    "Modo demostración: no hay una conversación grabada para "
                    f"«{solicitud.mensaje.strip()}». "
                    "Elige una de las preguntas sugeridas para ver su "
                    "respuesta y traza paso a paso."
                )
                yield _evento("final", {
                    "texto": aviso,
                    "modo_demo": True,
                    "coincidencia_demo": False,
                    "aviso_demo": aviso,
                }, estado)
                return
            pregunta_grabada = traza.get("pregunta", "consulta guardada")
            aviso_demo = (
                f"Modo demostración: conversación grabada para «{pregunta_grabada}»"
            )
            coincidencia_demo = traza.get("coincidencia_demo", False)
            # El aviso debe llegar antes de la traza grabada, porque sus pasos
            # pertenecen a otra conversación cuando la consulta no coincide.
            aviso_evento = {
                "fase": "PERCEPCION",
                "evento": "reproduccion_demo",
                "modo_demo": True,
                "aviso_demo": aviso_demo,
                "pregunta_original": solicitud.mensaje,
                "pregunta_grabada": pregunta_grabada,
                "coincidencia_demo": coincidencia_demo,
            }
            estado.agregar_evento(aviso_evento)
            yield _evento("paso", {"traza": aviso_evento}, estado)
            pregunta_evento = {
                "fase": "PERCEPCION",
                "evento": "tarea_recibida",
                "pregunta": solicitud.mensaje,
                "modo_demo": True,
            }
            eventos = traza["eventos"]
            if not any(
                paso.get("evento") == "tarea_recibida" for paso in eventos
            ):
                estado.agregar_evento(pregunta_evento)
                yield _evento("paso", {"traza": pregunta_evento}, estado)
            for paso in eventos:
                estado.agregar_evento(paso)
                yield _evento("paso", {"traza": paso}, estado)
            respuesta_final = traza.get("respuesta_final") or (
                "El presupuesto diario se agotó; esta respuesta reproduce "
                "una traza de demostración."
            )
            evento_final = {
                "fase": "ACCION",
                "evento": "respuesta_final",
                "texto": respuesta_final,
                "modo_demo": True,
                "traza_demo": traza["id"],
                "aviso_demo": aviso_demo,
                "coincidencia_demo": coincidencia_demo,
                "pregunta_grabada": pregunta_grabada,
            }
            estado.agregar_evento(evento_final)
            yield _evento("final", {
                "texto": respuesta_final,
                "modo_demo": True,
                "traza_demo": traza["id"],
                "aviso_demo": aviso_demo,
                "coincidencia_demo": coincidencia_demo,
                "pregunta_grabada": pregunta_grabada,
            }, estado)

        return _RespuestaSSEProtegida(
            transmitir(),
            estado,
            trabajador_iniciado,
            cancel_event,
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/semanas")
    def semanas() -> list[dict]:
        filas = estado.repo_demo.con.execute(
            "SELECT semana, total, datos_incompletos, alerto, tardias "
            "FROM semanas ORDER BY semana"
        ).fetchall()
        return [
            {
                "semana": fila["semana"],
                "total": fila["total"],
                "datos_incompletos": bool(fila["datos_incompletos"]),
                "alerto": bool(fila["alerto"]),
                "tardias": fila["tardias"],
            }
            for fila in filas
        ]

    @router.post("/cierre")
    def cierre(
        solicitud: SolicitudCierre,
        codigo: str | None = Header(default=None, alias="X-Codigo-Acceso"),
    ) -> dict:
        _autorizar(estado, codigo)
        _ocupado(estado)
        try:
            semana = estado.repo_demo.semana(solicitud.semana)
            if semana is None:
                raise HTTPException(status_code=404, detail="No hay datos para esa semana.")
            from datetime import datetime, timezone

            ahora = datetime.now(timezone.utc)
            manejador = ManejadorAgente(estado.llm, lambda: estado.contexto())
            respaldo = not manejador.al_cerrar(
                solicitud.semana, ahora, bool(semana["datos_incompletos"])
            )
            if respaldo:
                contexto = estado.contexto()
                determinista = ManejadorDeterminista(
                    contexto.repo, contexto.notificador, contexto.reportes, contexto.cfg
                )
                determinista.al_cerrar(
                    solicitud.semana, ahora, bool(semana["datos_incompletos"])
                )
            reporte = next(
                (
                    item for item in estado.repo_demo.reportes()
                    if item["semana"] == solicitud.semana
                ),
                None,
            )
            return {
                "semana": solicitud.semana,
                "estado": "cerrado",
                "etiqueta": (
                    "provisional" if semana["datos_incompletos"] else "final"
                ),
                "respaldo": respaldo,
                "modo_demo": estado.presupuesto_agotado(),
                "reporte_existente": reporte is not None,
            }
        except HTTPException:
            raise
        except Exception as exc:
            _LOG.error("Fallo controlado durante cierre API: %s", type(exc).__name__)
            raise HTTPException(
                status_code=500, detail="No fue posible completar el cierre."
            ) from None
        finally:
            estado.candado.release()

    @router.get("/resultados")
    def resultados() -> list[dict]:
        return [
            {
                "semana": reporte["semana"],
                "generado_en": estado.texto_seguro(reporte["generado_en"]),
                "archivo": estado.texto_seguro(Path(reporte["ruta"]).name),
                "etiqueta": (
                    "provisional" if reporte["incompleto"] else "final"
                ),
            }
            for reporte in estado.repo_demo.reportes()
        ]

    @router.post("/reiniciar")
    def reiniciar(
        codigo: str | None = Header(default=None, alias="X-Codigo-Acceso"),
    ) -> dict:
        _autorizar(estado, codigo)
        _ocupado(estado)
        try:
            estado.reiniciar_demo()
            return {"estado": "reiniciado"}
        except Exception as exc:
            _LOG.error("Fallo controlado al reiniciar demo: %s", type(exc).__name__)
            raise HTTPException(
                status_code=500, detail="No fue posible reiniciar el demo."
            ) from None
        finally:
            estado.candado.release()

    @router.get("/demo")
    def demo() -> dict:
        return {
            "modo_demo": estado.presupuesto_agotado(),
            "traza": estado.traza_publica(),
        }

    return router
