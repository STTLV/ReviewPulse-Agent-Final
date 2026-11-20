from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(repr=False)
class Ajustes:
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_juez_model: str
    app_codigo_acceso: str
    llm_tope_tokens_dia: int

    def __repr__(self) -> str:
        return (
            f"Ajustes(llm_base_url={self.llm_base_url!r}, llm_api_key='***', "
            f"llm_model={self.llm_model!r}, llm_juez_model={self.llm_juez_model!r}, "
            f"app_codigo_acceso='***', llm_tope_tokens_dia={self.llm_tope_tokens_dia!r})"
        )


def cargar_ajustes(fuentes: Mapping[str, object] | None = None) -> Ajustes:
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

    return Ajustes(
        llm_base_url=leer("LLM_BASE_URL"),
        llm_api_key=leer("LLM_API_KEY"),
        llm_model=leer("LLM_MODEL"),
        llm_juez_model=leer("LLM_JUEZ_MODEL"),
        app_codigo_acceso=leer("APP_CODIGO_ACCESO"),
        llm_tope_tokens_dia=max(0, limite),
    )
