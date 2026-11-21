"""Generación de informes con la infraestructura determinista de la Tarea 3."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .analisis import construir_reporte
from .registro import Contexto, ErrorHerramienta, herramienta
from .resenas import _existe_semana


class Generar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semana: int = Field(ge=0)


@herramienta("generar_reporte", "Genera un informe semanal determinista y su resumen JSON.", Generar)
def generar_reporte(entrada: Generar, ctx: Contexto) -> dict:
    if not _existe_semana(ctx, entrada.semana):
        # Antes de guardar el cierre en SQLite puede haber 0 reseñas.
        # No autorizar semanas inexistentes desde los argumentos del LLM.
        if (ctx.sesion.semana_en_cierre != entrada.semana
                or not ctx.sesion.incompleto):
            raise ErrorHerramienta("sin_datos", "No hay datos para esa semana.")
    ruta = construir_reporte(
        ctx.repo, ctx.reportes, entrada.semana, ctx.ahora,
        ctx.sesion.incompleto, ctx.cfg,
    )
    ruta = Path(ruta)
    resumen = json.loads(ruta.with_suffix(".json").read_text(encoding="utf-8"))
    # Evitar exponer carpetas locales, rutas absolutas y credenciales.
    return {"ruta": str(Path("reportes") / ruta.name), "resumen": resumen}
