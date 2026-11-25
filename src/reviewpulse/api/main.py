"""Factoría FastAPI de ReviewPulse."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..config import Ajustes, cargar_ajustes
from ..llm.cliente import ClienteLLM
from .estado import EstadoAPI
from .rutas import crear_router


def crear_app(ajustes: Ajustes, llm: ClienteLLM | None = None) -> FastAPI:
    estado = EstadoAPI(ajustes, llm)

    @asynccontextmanager
    async def ciclo_vida(app: FastAPI):
        try:
            yield
        finally:
            app.state.estado.cerrar()

    app = FastAPI(lifespan=ciclo_vida)
    app.state.estado = estado
    app.include_router(crear_router(estado))
    return app


def crear_app_desde_entorno() -> FastAPI:
    return crear_app(cargar_ajustes())
