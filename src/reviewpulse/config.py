from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Mapping

from dotenv import load_dotenv


@dataclass(repr=False)
class Ajustes:
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_juez_model: str
    app_codigo_acceso: str
    llm_tope_tokens_dia: int
    api_chat_timeout_s: float = 120.0

    def __repr__(self) -> str:
        return (
            f"Ajustes(llm_base_url={self.llm_base_url!r}, llm_api_key='***', "
            f"llm_model={self.llm_model!r}, llm_juez_model={self.llm_juez_model!r}, "
            f"app_codigo_acceso='***', llm_tope_tokens_dia={self.llm_tope_tokens_dia!r}, "
            f"api_chat_timeout_s={self.api_chat_timeout_s!r})"
        )


def cargar_ajustes(fuentes: Mapping[str, object] | None = None) -> Ajustes:
    load_dotenv()
    fuente = dict(fuentes or {})

    def leer(nombre: str, defecto: str = "") -> str:
        valor = fuente.get(nombre)
        if valor is not None:
            return str(valor)
        return os.getenv(nombre, defecto)

    limite_texto = leer("LLM_TOPE_TOKENS_DIA")
    try:
        limite = int(limite_texto)
    except (TypeError, ValueError):
        limite = 0

    timeout_texto = leer("API_CHAT_TIMEOUT_S", "120")
    try:
        timeout_chat = float(timeout_texto)
    except (TypeError, ValueError) as exc:
        raise ValueError("API_CHAT_TIMEOUT_S debe ser un número positivo.") from exc
    if not math.isfinite(timeout_chat) or timeout_chat <= 0:
        raise ValueError("API_CHAT_TIMEOUT_S debe ser un número positivo finito.")

    return Ajustes(
        llm_base_url=leer("LLM_BASE_URL"),
        llm_api_key=leer("LLM_API_KEY"),
        llm_model=leer("LLM_MODEL"),
        llm_juez_model=leer("LLM_JUEZ_MODEL"),
        app_codigo_acceso=leer("APP_CODIGO_ACCESO"),
        llm_tope_tokens_dia=max(0, limite),
        api_chat_timeout_s=timeout_chat,
    )
