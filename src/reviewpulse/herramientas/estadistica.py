"""Deteccion diaria de cambios mediante CUSUM."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ParamsCusum:
    delta: float
    h: float
    min_negativas: float


@dataclass
class ResultadoCusum:
    alarma: bool
    dia_alarma: int | None
    s_max: float
    p0: float
    p1: float
    serie: list[float]


def p0_suavizado(negativas: float, total: float) -> float:
    """Estima la proporcion historica suavizada."""
    if total < 0 or negativas < 0 or negativas > total:
        raise ValueError("Conteos historicos invalidos.")

    return (negativas + 1.0) / (total + 4.0)


def cusum_diario(
    dias: list[tuple[float, float]],
    p0: float,
    params: ParamsCusum,
) -> ResultadoCusum:
    """Acumula evidencia de un aumento en negativas por dia."""

    if not 0.0 <= p0 <= 1.0:
        raise ValueError("p0 debe estar entre 0 y 1.")

    if params.delta <= 0 or params.h <= 0:
        raise ValueError("delta y h deben ser positivos.")

    if params.min_negativas < 0:
        raise ValueError("min_negativas no puede ser negativo.")

    if p0 >= 0.95:
        return ResultadoCusum(
            alarma=False,
            dia_alarma=None,
            s_max=0.0,
            p0=p0,
            p1=p0,
            serie=[0.0] * len(dias),
        )

    p0_ajustado = max(1e-6, p0)
    p1 = min(0.95, p0_ajustado + params.delta)

    s = 0.0
    s_max = 0.0
    negativas_acumuladas = 0.0
    serie = []

    for indice, (negativas, total) in enumerate(dias):
        if total < 0 or negativas < 0 or negativas > total:
            raise ValueError("Conteos diarios invalidos.")

        negativas_acumuladas += negativas

        if total > 0:
            w = (
                negativas * math.log(p1 / p0_ajustado)
                + (total - negativas)
                * math.log((1.0 - p1) / (1.0 - p0_ajustado))
            )

            s = max(0.0, s + w)

        serie.append(s)
        s_max = max(s_max, s)

        if (
            s >= params.h
            and negativas_acumuladas >= params.min_negativas
        ):
            return ResultadoCusum(
                alarma=True,
                dia_alarma=indice,
                s_max=s_max,
                p0=p0_ajustado,
                p1=p1,
                serie=serie,
            )

    return ResultadoCusum(
        alarma=False,
        dia_alarma=None,
        s_max=s_max,
        p0=p0_ajustado,
        p1=p1,
        serie=serie,
    )
