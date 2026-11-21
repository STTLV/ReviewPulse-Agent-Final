"""Emisión de alertas condicionada a una comparación positiva en la sesión."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .analisis import comparar_temas, registrar_alerta
from .registro import Contexto, ErrorHerramienta, herramienta
from .resenas import Tema, _existe_semana


class Emitir(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semana: int = Field(ge=0)
    tema: Tema
    justificacion: str = Field(min_length=1, max_length=2000)


@herramienta("emitir_alerta", "Emite alerta solo tras una comparación CUSUM positiva en esta sesión.", Emitir)
def emitir_alerta(entrada: Emitir, ctx: Contexto) -> dict:
    clave = (entrada.semana, entrada.tema)
    if clave not in ctx.sesion.comparaciones_positivas:
        raise ErrorHerramienta("rechazada", "Debe comparar la semana y obtener una alarma positiva antes de alertar.")
    if not _existe_semana(ctx, entrada.semana):
        raise ErrorHerramienta("sin_datos", "No hay datos para esa semana.")
    if any(a["semana"] == entrada.semana and a["tema"] == entrada.tema for a in ctx.repo.alertas()):
        raise ErrorHerramienta("rechazada", "La alerta de esa semana y tema ya existe.")
    comparacion = ctx.sesion.comparaciones.get(clave)
    if comparacion is None:
        # Las pruebas pueden construir una Sesion con la comparación positiva preautorizada.
        comparacion = comparar_temas(ctx.repo, entrada.semana, ctx.cfg)[entrada.tema]
    comparacion = {**comparacion, "alarma": True}
    alerta = registrar_alerta(
        ctx.repo, ctx.notificador, entrada.semana, entrada.tema,
        comparacion, ctx.ahora, "a_tiempo",
    )
    return {"semana": entrada.semana, "tema": entrada.tema, "mensaje": alerta["mensaje"], "emitida": True}
