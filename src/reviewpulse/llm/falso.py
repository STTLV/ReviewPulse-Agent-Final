from __future__ import annotations

import re

from collections.abc import Callable

from .cliente import LlamadaHerramienta, RespuestaLLM, Uso


def respuesta_texto(texto: str) -> RespuestaLLM:
    return RespuestaLLM(True, texto, [], Uso(0, 0),
                        mensaje_asistente={"role": "assistant", "content": texto})


def respuesta_herramienta(nombre: str, **args) -> RespuestaLLM:
    import json

    argumentos = json.dumps(args, ensure_ascii=False)
    llamada = LlamadaHerramienta("llamada-falsa", nombre, argumentos)
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
    def __init__(self, guion: list[RespuestaLLM | Exception | Callable[[list[dict]], RespuestaLLM]]):
        self.guion = list(guion)
        self.llamadas: list[list[dict]] = []
        self._etapa_operativa = {}

    def chat(self, mensajes: list[dict], herramientas: list[dict] | None = None,
             modelo: str | None = None) -> RespuestaLLM:
        self.llamadas.append(list(mensajes))
        if not self.guion:
            return respuesta_texto("")
        siguiente = self.guion.pop(0)
        if isinstance(siguiente, BaseException):
            raise siguiente
        if callable(siguiente):
            return siguiente(mensajes)
        return siguiente

    def guion_operativo(self, mensajes: list[dict]) -> RespuestaLLM:
        texto = "\n".join(str(m.get("content", "")) for m in mensajes if m.get("content"))
        if "error" in texto.lower():
            return RespuestaLLM(False, error="operacion simulada fallida")
        alarma = re.search(r"ALARMA\s+semana\s*=\s*(\d+)\s+tema\s*=\s*([^\s]+)", texto, re.I)
        if alarma:
            semana, tema = alarma.groups()
            clave = ("alarma", semana, tema)
            if self._etapa_operativa.get(clave, 0) == 0:
                self._etapa_operativa[clave] = 1
                observaciones = re.search(r"observaciones\s*=\s*(\d+)", texto, re.I)
                args = {"semana": int(semana), "tema": tema}
                if observaciones:
                    args["observaciones"] = int(observaciones.group(1))
                return respuesta_herramienta("comparar_semana", **args)
            self._etapa_operativa[clave] = 2
            return respuesta_herramienta("emitir_alerta", semana=int(semana), tema=tema)
        cierre = re.search(r"CIERRE\s+semana\s*=\s*(\d+)\s+incompleto\s*=\s*(\d+)", texto, re.I)
        if cierre:
            semana, incompleto = cierre.groups()
            return respuesta_herramienta("generar_reporte", semana=int(semana),
                                         incompleto=int(incompleto))
        if re.search(r"(?:genera(?:r)?|generar)\s+(?:el\s+)?reporte", texto, re.I):
            return respuesta_herramienta("generar_reporte")
        return respuesta_texto("No hay una tarea operativa reconocida")
