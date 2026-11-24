from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol

from ..config import Ajustes


@dataclass
class Uso:
    entrada: int
    salida: int


@dataclass
class LlamadaHerramienta:
    id: str
    nombre: str
    argumentos_crudos: str


@dataclass
class RespuestaLLM:
    ok: bool
    texto: str | None = None
    llamadas: list[LlamadaHerramienta] | None = None
    uso: Uso | None = None
    error: str | None = None
    mensaje_asistente: dict | None = None

    def __post_init__(self) -> None:
        if self.llamadas is None:
            self.llamadas = []


class ClienteLLM(Protocol):
    def chat(self, mensajes: list[dict], herramientas: list[dict] | None = None,
             modelo: str | None = None) -> RespuestaLLM:
        ...


class ClienteOpenAI:
    def __init__(self, ajustes: Ajustes, sdk=None, max_intentos: int | None = None):
        if max_intentos is not None and max_intentos < 1:
            raise ValueError("max_intentos debe ser al menos 1")
        self.ajustes = ajustes
        self.max_intentos = max_intentos or 3
        self.solicitudes = 0
        if sdk is None:
            if not ajustes.llm_api_key:
                self.sdk = None
                return
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("Instala el paquete opcional 'openai' para usar ClienteOpenAI") from exc
            parametros = {"api_key": ajustes.llm_api_key}
            if ajustes.llm_base_url:
                parametros["base_url"] = ajustes.llm_base_url
            if max_intentos is not None:
                # En capturas limitadas, desactiva también los reintentos internos
                # del SDK para que el tope cuente solicitudes HTTP reales.
                parametros["max_retries"] = 0
            sdk = OpenAI(**parametros)
        self.sdk = sdk

    def chat(self, mensajes: list[dict], herramientas: list[dict] | None = None,
             modelo: str | None = None) -> RespuestaLLM:
        if (
            not self.ajustes.llm_base_url
            or not self.ajustes.llm_api_key
            or not (modelo or self.ajustes.llm_model)
            or self.ajustes.llm_tope_tokens_dia <= 0
        ):
            return RespuestaLLM(False, error="no_configurado")
        parametros = {
            "model": modelo or self.ajustes.llm_model,
            "messages": mensajes,
            "temperature": 0,
            "timeout": 60,
        }
        if herramientas:
            parametros["tools"] = herramientas
        ultimo_error = None
        for intento in range(1, self.max_intentos + 1):
            try:
                self.solicitudes += 1
                respuesta = self.sdk.chat.completions.create(**parametros)
            except Exception as exc:
                ultimo_error = exc
                codigo = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                if isinstance(codigo, str):
                    try:
                        codigo = int(codigo)
                    except ValueError:
                        codigo = None
                tipo = exc.__class__.__name__
                if codigo in (401, 402, 403):
                    return self._respuesta_error(exc, codigo)
                if tipo in {"BadRequestError", "ContextLengthExceededError"}:
                    return self._respuesta_error(exc, codigo)
                if intento < self.max_intentos:
                    time.sleep(0.5 * intento)
                    continue
                return self._respuesta_error(exc, codigo)
            else:
                return self._respuesta_exito(respuesta)
        return self._respuesta_error(ultimo_error, None)

    def _respuesta_exito(self, respuesta) -> RespuestaLLM:
        choice = respuesta.choices[0]
        mensaje = choice.message
        if isinstance(mensaje, dict):
            texto = mensaje.get("content")
            llamadas_raw = mensaje.get("tool_calls") or []
        else:
            texto = getattr(mensaje, "content", None)
            llamadas_raw = getattr(mensaje, "tool_calls", None) or []
        llamadas = []
        llamadas_dict = []
        for llamada in llamadas_raw:
            if isinstance(llamada, dict):
                identificador = llamada.get("id", "")
                funcion = llamada.get("function") or {}
                nombre = funcion.get("name", "")
                argumentos = funcion.get("arguments", "{}")
            else:
                identificador = getattr(llamada, "id", "")
                funcion = getattr(llamada, "function", None)
                nombre = getattr(funcion, "name", "")
                argumentos = getattr(funcion, "arguments", "{}")
            argumentos = argumentos if isinstance(argumentos, str) else json.dumps(argumentos)
            llamadas.append(LlamadaHerramienta(identificador, nombre, argumentos))
            llamadas_dict.append({
                "id": identificador,
                "type": "function",
                "function": {"name": nombre, "arguments": argumentos},
            })
        mensaje_asistente = {"role": "assistant", "content": texto}
        if llamadas_dict:
            mensaje_asistente["tool_calls"] = llamadas_dict
        usage = getattr(respuesta, "usage", None)
        if isinstance(usage, dict):
            entrada = usage.get("prompt_tokens", 0)
            salida = usage.get("completion_tokens", 0)
        else:
            entrada = getattr(usage, "prompt_tokens", 0) if usage else 0
            salida = getattr(usage, "completion_tokens", 0) if usage else 0
        return RespuestaLLM(
            True,
            texto,
            llamadas,
            Uso(entrada or 0, salida or 0),
            mensaje_asistente=mensaje_asistente,
        )

    def _respuesta_error(self, exc, codigo) -> RespuestaLLM:
        tipo = exc.__class__.__name__
        if codigo in (401, 403) or tipo in {"AuthenticationError", "PermissionDeniedError"}:
            error = "autenticacion"
        else:
            error = "proveedor"
        return RespuestaLLM(False, error=error)
