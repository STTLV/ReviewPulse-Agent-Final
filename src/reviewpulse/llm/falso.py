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


def _resultado_correcto(contenido: str) -> dict | None:
    """Lee el sobre de ejecutar() sin confundir ok=True con alarma=True."""
    try:
        respuesta = json.loads(contenido)
    except (TypeError, ValueError):
        return None
    if not isinstance(respuesta, dict) or respuesta.get("ok") is not True:
        return None
    datos = respuesta.get("datos")
    return datos if isinstance(datos, dict) else None


def _hubo_alarma(contenido: str, tema: str) -> bool:
    """Solo acepta la señal booleana del tema solicitado."""
    datos = _resultado_correcto(contenido)
    comparacion = datos.get(tema) if datos is not None else None
    return isinstance(comparacion, dict) and comparacion.get("alarma") is True


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
            return respuesta_herramienta("comparar_semana", semana=int(semana), tema=tema)

        comparacion_id, _ = comparaciones[-1]
        if comparacion_id not in resultados:
            return respuesta_texto("La comparación está pendiente; no se emitió ninguna alerta.")
        if not _hubo_alarma(resultados[comparacion_id], tema):
            return respuesta_texto(f"No hubo alarma en la semana {semana}; no se emitió alerta.")

        alertas = [(call_id, name) for call_id, name in llamadas if name == "emitir_alerta"]
        if not alertas:
            return respuesta_herramienta(
                "emitir_alerta", semana=int(semana), tema=tema,
                justificacion="CUSUM positivo confirmado con comparar_semana",
            )
        alerta_id, _ = alertas[-1]
        if alerta_id in resultados:
            datos_alerta = _resultado_correcto(resultados[alerta_id])
            if datos_alerta is not None and datos_alerta.get("emitida") is True:
                return respuesta_texto(f"Alerta emitida para {tema}, semana {semana}.")
            return respuesta_texto("No se pudo emitir la alerta; la herramienta devolvió un error.")
        return respuesta_texto("La alerta fue solicitada.")

    cierre = re.search(r"CIERRE\s+semana\s*=\s*(\d+)\s+incompleto\s*=\s*(\d+)", texto_usuario, re.I)
    if cierre:
        semana, _incompleto = cierre.groups()
        reportes = [(call_id, name) for call_id, name in llamadas if name == "generar_reporte"]
        if not reportes:
            return respuesta_herramienta("generar_reporte", semana=int(semana))
        reporte_id, _ = reportes[-1]
        if reporte_id in resultados:
            datos_reporte = _resultado_correcto(resultados[reporte_id])
            if datos_reporte is not None and "resumen" in datos_reporte and "ruta" in datos_reporte:
                return respuesta_texto(f"Reporte de la semana {semana} generado.")
            return respuesta_texto("No se pudo generar el reporte; la herramienta devolvió un error.")
        return respuesta_texto(f"El reporte de la semana {semana} fue solicitado.")

    if re.search(r"(?:genera(?:r)?|generar)\s+(?:el\s+)?reporte", texto_usuario, re.I):
        reportes = [(identificador, nombre) for identificador, nombre in llamadas
                    if nombre == "generar_reporte"]
        if reportes:
            ultimo_id, _ = reportes[-1]
            datos = _resultado_correcto(resultados.get(ultimo_id, ""))
            if datos is not None and "resumen" in datos and "ruta" in datos:
                return respuesta_texto("Reporte generado.")
            return respuesta_texto("No se pudo generar el reporte.")
        return respuesta_herramienta("generar_reporte")
    return respuesta_texto("No hay una tarea operativa reconocida.")
