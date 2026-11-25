"""Factoría FastAPI de ReviewPulse."""
from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
    montar_interfaz(app)
    return app


def crear_app_desde_entorno() -> FastAPI:
    return crear_app(cargar_ajustes())


def montar_interfaz(app: FastAPI) -> None:
    """Interfaz estática T11, sin framework de frontend ni CDN."""
    carpeta_web = Path(__file__).resolve().parents[1] / "web"
    app.mount(
        "/assets", StaticFiles(directory=str(carpeta_web), check_dir=True),
        name="reviewpulse-assets",
    )

    @app.get("/", include_in_schema=False)
    def inicio() -> FileResponse:
        return FileResponse(
            carpeta_web / "index.html", media_type="text/html",
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": (
                    "default-src 'none'; base-uri 'none'; form-action 'none'; "
                    "style-src 'self'; script-src 'self'; connect-src 'self'; "
                    "img-src 'self' data:; font-src 'self'; frame-ancestors 'none'"
                ),
            },
        )
