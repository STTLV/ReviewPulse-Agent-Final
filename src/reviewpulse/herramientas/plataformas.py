"""Estado simulado de conectores, sin confundir ausencia de datos con disponibilidad."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ..entorno import PLATAFORMAS
from .registro import Contexto, herramienta


class Estado(BaseModel):
    model_config = ConfigDict(extra="forbid")


@herramienta("estado_plataformas", "Consulta la disponibilidad actual y último dato real de cada plataforma.", Estado)
def estado_plataformas(entrada: Estado, ctx: Contexto) -> dict:
    filas = ctx.repo.resenas()
    salida = {}
    for plataforma in PLATAFORMAS:
        fechas = [f["fecha"] for f in filas if f["plataforma"] == plataforma]
        salida[plataforma] = {
            "disponible": bool(ctx.entorno.disponible(plataforma, ctx.ahora)),
            "ultimo_dato": max(fechas) if fechas else None,
        }
    return salida
