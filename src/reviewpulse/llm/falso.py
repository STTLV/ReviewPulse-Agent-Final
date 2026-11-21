from __future__ import annotations

import json
import re
from collections.abc import Callable
from uuid import uuid4

from .cliente import LlamadaHerramienta, RespuestaLLM, Uso


def respuesta_texto(texto: str) -> RespuestaLLM:
    return RespuestaLLM(True, texto, [], Uso(0, 0),
                        mensaje_asistente={"role": "assistant", "content": texto})


def respuesta_herramienta(nombre: str, **args) -> RespuestaLLM:
    argumentos = json.dumps(args, ensure_ascii=False)
    llamada = LlamadaHerramienta(f"llamada-{uuid4().hex}", nombre, argumentos)
    return RespuestaLLM(
        True,
        None,
        [llamada],
        Uso(0, 0),
        mensaje_asistente={
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": llamada.id,
                "type": "function",
                "function": {"name": nombre, "arguments": argumentos},
            }],
        },
    )


class LLMFalso:
    def __init__(self, guion: list[RespuestaLLM | Exception | Callable[[list[dict]], RespuestaLLM]] | Callable[[list[dict]], RespuestaLLM]):
        self.guion = guion if callable(guion) else list(guion)
        self.llamadas: list[list[dict]] = []

    def chat(self, mensajes: list[dict], herramientas: list[dict] | None = None,
             modelo: str | None = None) -> RespuestaLLM:
        self.llamadas.append(list(mensajes))
        if callable(self.guion):
            siguiente = self.guion(mensajes)
        else:
            if not self.guion:
                return respuesta_texto("")
            siguiente = self.guion.pop(0)
        if isinstance(siguiente, BaseException):
            raise siguiente
        if callable(siguiente):
            return siguiente(mensajes)
        return siguiente


def _llamadas_previas(mensajes: list[dict]) -> list[tuple[str, str]]:
    llamadas = []
    for mensaje in mensajes:
        if mensaje.get("role") != "assistant":
            continue
        for llamada in mensaje.get("tool_calls", []) or []:
            funcion = llamada.get("function") or {}
            llamadas.append((llamada.get("id", ""), funcion.get("name", "")))
    return llamadas


def _resultados_herramientas(mensajes: list[dict]) -> dict[str, str]:
    return {
        str(mensaje.get("tool_call_id", "")): str(mensaje.get("content", ""))
        for mensaje in mensajes
        if mensaje.get("role") == "tool"
    }


def _hubo_alarma(contenido: str) -> bool:
    try:
        datos = json.loads(contenido)
    except (TypeError, json.JSONDecodeError):
        datos = None

    if isinstance(datos, dict):
        for clave in ("hubo_alarma", "alarma", "alerta"):
            valor = datos.get(clave)
            if isinstance(valor, bool):
                return valor
            if isinstance(valor, str):
                valor = valor.strip().lower()
                if valor in {"true", "si", "sí", "yes", "alarma"}:
                    return True
                if valor in {"false", "no", "sin alarma", "ninguna"}:
                    return False
        for clave in ("temas_en_alerta", "alarmas", "alertas"):
            valor = datos.get(clave)
            if isinstance(valor, list):
                return bool(valor)

    normalizado = contenido.strip().lower()
    if any(frase in normalizado for frase in ("sin alarma", "no hubo alarma", "no se emitira alerta")):
        return False
    return bool(re.search(r"\b(true|si|sí|yes|hubo alarma|alarma detectada)\b", normalizado))


def guion_operativo(mensajes: list[dict]) -> RespuestaLLM:
    texto_usuario = "\n".join(
        str(mensaje.get("content", ""))
        for mensaje in mensajes
        if mensaje.get("role") == "user" and mensaje.get("content")
    )
    llamadas = _llamadas_previas(mensajes)
    resultados = _resultados_herramientas(mensajes)

    alarma = re.search(r"ALARMA\s+semana\s*=\s*(\d+)\s+tema\s*=\s*([^\s]+)", texto_usuario, re.I)
    if alarma:
        semana, tema = alarma.groups()
        comparaciones = [(call_id, name) for call_id, name in llamadas if name == "comparar_semana"]
        if not comparaciones:
            observaciones = re.search(r"(?:n_)?observaciones\s*=\s*(\d+)", texto_usuario, re.I)
            argumentos = {"semana": int(semana), "tema": tema}
            if observaciones:
                argumentos["observaciones"] = int(observaciones.group(1))
            return respuesta_herramienta("comparar_semana", **argumentos)

        comparacion_id, _ = comparaciones[-1]
        if comparacion_id not in resultados:
            return respuesta_texto("La comparación está pendiente; no se emitió ninguna alerta.")
        if not _hubo_alarma(resultados[comparacion_id]):
            return respuesta_texto(f"No hubo alarma en la semana {semana}; no se emitió alerta.")

        alertas = [(call_id, name) for call_id, name in llamadas if name == "emitir_alerta"]
        if not alertas:
            return respuesta_herramienta("emitir_alerta", semana=int(semana), tema=tema)
        alerta_id, _ = alertas[-1]
        if alerta_id in resultados:
            return respuesta_texto(f"Alerta emitida para {tema}, semana {semana}.")
        return respuesta_texto("La alerta fue solicitada.")

    cierre = re.search(r"CIERRE\s+semana\s*=\s*(\d+)\s+incompleto\s*=\s*(\d+)", texto_usuario, re.I)
    if cierre:
        semana, incompleto = cierre.groups()
        reportes = [(call_id, name) for call_id, name in llamadas if name == "generar_reporte"]
        if not reportes:
            return respuesta_herramienta(
                "generar_reporte",
                semana=int(semana),
                incompleto=int(incompleto),
            )
        reporte_id, _ = reportes[-1]
        if reporte_id in resultados:
            return respuesta_texto(f"Reporte de la semana {semana} generado.")
        return respuesta_texto(f"El reporte de la semana {semana} fue solicitado.")

    if re.search(r"(?:genera(?:r)?|generar)\s+(?:el\s+)?reporte", texto_usuario, re.I):
        if any(name == "generar_reporte" for _, name in llamadas):
            return respuesta_texto("Reporte generado.")
        return respuesta_herramienta("generar_reporte")
    return respuesta_texto("No hay una tarea operativa reconocida.")
