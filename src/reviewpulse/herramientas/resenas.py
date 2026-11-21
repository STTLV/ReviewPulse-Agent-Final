"""Consultas y clasificación de reseñas para el agente."""
from __future__ import annotations

from html import escape
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..corpus import TEMAS
from ..preprocesamiento import enmascarar_nombres, validar
from .registro import Contexto, ErrorHerramienta, herramienta


Tema = Literal["limpieza", "servicio", "ubicacion", "precio"]
Polaridad = Literal["positiva", "neutra", "negativa"]
Plataforma = Literal["TripAdvisor", "Google"]


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semana: int | None = Field(default=None, ge=0)
    tema: Tema | None = None
    polaridad: Polaridad | None = None
    plataforma: Plataforma | None = None


class Contar(_Entrada):
    pass


class Buscar(_Entrada):
    texto_contiene: str | None = Field(default=None, max_length=200)
    limite: int = Field(default=5, ge=1, le=10)


class Clasificar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texto: str = Field(min_length=1, max_length=10000)


def _existe_semana(ctx: Contexto, semana: int) -> bool:
    if ctx.repo.semana(semana) is not None:
        return True
    f = ctx.repo.con.execute("SELECT 1 FROM resenas WHERE semana=? LIMIT 1", (semana,)).fetchone()
    return f is not None


def _seleccionar(ctx: Contexto, entrada: _Entrada) -> list[dict]:
    if entrada.semana is not None and not _existe_semana(ctx, entrada.semana):
        raise ErrorHerramienta("sin_datos", "No hay datos para la semana solicitada.")
    filas = ctx.repo.resenas()
    return [
        fila for fila in filas
        if (entrada.semana is None or fila["semana"] == entrada.semana)
        and (entrada.tema is None or fila["tema"] == entrada.tema)
        and (entrada.polaridad is None or fila["polaridad"] == entrada.polaridad)
        and (entrada.plataforma is None or fila["plataforma"] == entrada.plataforma)
    ]


@herramienta("contar_resenas", "Cuenta reseñas existentes con filtros; no inventa cifras.", Contar)
def contar_resenas(entrada: Contar, ctx: Contexto) -> dict:
    filas = _seleccionar(ctx, entrada)
    if entrada.semana is None and not ctx.repo.resenas():
        raise ErrorHerramienta("sin_datos", "Aún no hay reseñas almacenadas.")
    return {
        "total": len(filas),
        "por_tema": {tema: sum(f["tema"] == tema for f in filas) for tema in TEMAS},
        "por_polaridad": {
            p: sum(f["polaridad"] == p for f in filas) for p in ("positiva", "neutra", "negativa")
        },
    }


@herramienta("buscar_resenas", "Recupera hasta 10 reseñas desidentificadas y delimitadas como datos.", Buscar)
def buscar_resenas(entrada: Buscar, ctx: Contexto) -> list[dict]:
    filas = _seleccionar(ctx, entrada)
    if entrada.texto_contiene:
        termino = entrada.texto_contiene.casefold()
        filas = [f for f in filas if termino in f["texto"].casefold()]
    if entrada.semana is None and not ctx.repo.resenas():
        raise ErrorHerramienta("sin_datos", "Aún no hay reseñas almacenadas.")
    return [
        {
            "id": f["id"],
            "fecha": f["fecha"],
            "texto": f"<resena>{escape(enmascarar_nombres(f['texto']))}</resena>",
            "polaridad": f["polaridad"],
            "tema": f["tema"],
            "confianza": f["confianza"],
        }
        for f in filas[: entrada.limite]
    ]


@herramienta("clasificar_resena", "Clasifica un texto válido sin guardarlo automáticamente.", Clasificar)
def clasificar_resena(entrada: Clasificar, ctx: Contexto) -> dict:
    valida, texto, _motivo = validar({"fecha": ctx.ahora.isoformat(), "texto": entrada.texto})
    if not valida:
        raise ErrorHerramienta("rechazada", "El texto no cumple los criterios de clasificación.")
    preds = ctx.modelo.predecir([texto])
    if len(preds) != 1:
        raise RuntimeError("El clasificador no devolvió una predicción.")
    pred = preds[0]
    umbral = float(ctx.cfg.get("umbral_confianza", 0.55))
    return {
        "polaridad": pred.polaridad,
        "tema": pred.tema,
        "confianza": float(pred.confianza),
        "revision_manual": bool(pred.confianza < umbral),
    }
