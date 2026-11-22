"""Rutas HTTP de ReviewPulse."""
from __future__ import annotations

import json
import logging
import queue
import threading
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
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
        _ocupado(estado)

        def transmitir():
            if estado.presupuesto_agotado():
                try:
                    texto = estado.texto_seguro(
                        "El presupuesto diario se agotó; esta respuesta usa modo demo."
                    )
                    paso = {
                        "fase": "SISTEMA",
                        "evento": "modo_demo",
                        "modo_demo": True,
                    }
                    estado.agregar_evento(paso)
                    yield _evento("paso", paso, estado)
                    yield _evento(
                        "final", {"texto": texto, "modo_demo": True}, estado
                    )
                finally:
                    estado.candado.release()
                return

            eventos: queue.Queue[tuple[str, object]] = queue.Queue()

            def emitir_paso(evento: dict) -> None:
                estado.agregar_evento(evento)
                eventos.put(("paso", evento))

            def ejecutar_agente() -> None:
                try:
                    resultado = resolver(
                        solicitud.mensaje,
                        estado.llm,
                        estado.contexto(),
                        traza=Traza(),
                        al_evento=emitir_paso,
                    )
                    eventos.put(("resultado", resultado))
                except Exception as exc:
                    _LOG.error("Fallo interno del agente API: %s", type(exc).__name__)
                    eventos.put(("fallo", None))
                finally:
                    estado.candado.release()

            trabajador = threading.Thread(target=ejecutar_agente, daemon=True)
            trabajador.start()
            while True:
                tipo, valor = eventos.get()
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
                        yield _evento("paso", {
                            "fase": "SISTEMA",
                            "evento": "modo_demo",
                            "modo_demo": True,
                        }, estado)
                        yield _evento("final", {
                            "texto": estado.texto_seguro(
                                "El presupuesto diario se agotó; esta respuesta usa modo demo."
                            ),
                            "modo_demo": True,
                        }, estado)
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

        return StreamingResponse(
            transmitir(),
            media_type="text/event-stream",
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
