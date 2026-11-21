"""Operaciones deterministas sobre reseñas, CUSUM y reportes desde SQLite.

No dependen del proveedor LLM. Toda cifra procede de RepositorioHistorico.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..actuadores import GeneradorReporte, Notificador
from ..corpus import TEMAS
from ..entorno import texto_semana
from ..memoria import RepositorioHistorico
from .estadistica import ParamsCusum, cusum_diario, p0_suavizado


def comparar_temas(repo: RepositorioHistorico, semana: int, cfg: dict) -> dict[str, dict]:
    """Compara el CUSUM diario contra semanas cerradas no alertadas."""
    conteos = repo.conteos_semana(semana)
    historial = repo.historial(semana, int(cfg["semanas_historial"]))
    params = ParamsCusum(
        delta=float(cfg["cusum_delta"]),
        h=float(cfg["cusum_h"]),
        min_negativas=float(cfg["cusum_min_negativas"]),
    )
    salida: dict[str, dict] = {}
    for tema in TEMAS:
        c = conteos[tema]
        total = float(sum(c.values()))
        negativas = float(c["negativa"])
        prop = negativas / total if total else 0.0
        props = [
            h["conteos"][tema]["negativa"] / sum(h["conteos"][tema].values())
            for h in historial if sum(h["conteos"][tema].values()) > 0
        ]
        promedio = sum(props) / len(props) if props else 0.0
        n_hist = sum(sum(h["conteos"][tema].values()) for h in historial)
        neg_hist = sum(h["conteos"][tema]["negativa"] for h in historial)
        p0 = p0_suavizado(neg_hist, n_hist)
        resultado = cusum_diario(repo.conteos_diarios(semana, tema), p0, params)
        motivos: list[str] = []
        if len(historial) < int(cfg["min_semanas_historial"]):
            motivos.append("historial_insuficiente")
        if total <= 0:
            motivos.append("sin_datos")
        if not resultado.alarma:
            motivos.append("cusum_sin_alarma")
        salida[tema] = {
            "total": total,
            "negativas": negativas,
            "proporcion": prop,
            "promedio": promedio,
            "p0": resultado.p0,
            "p1": resultado.p1,
            "s_max": resultado.s_max,
            "h": params.h,
            "dia_alarma": resultado.dia_alarma,
            "alarma": not motivos,
            "semanas_historial": len(historial),
            "motivos_no_alerta": motivos,
        }
    return salida


def registrar_alerta(
    repo: RepositorioHistorico,
    notificador: Notificador,
    semana: int,
    tema: str,
    comparacion: dict,
    ahora: datetime,
    tipo: str,
) -> dict:
    """Notifica y registra una nueva alerta; nunca la duplica."""
    existentes = {(a["semana"], a["tema"]) for a in repo.alertas()}
    if (semana, tema) in existentes:
        raise ValueError("La alerta de esta semana y tema ya fue emitida.")
    if not comparacion.get("alarma", False):
        raise ValueError("No se puede emitir alerta sin CUSUM confirmado.")
    alerta = {
        "semana": semana,
        "semana_texto": texto_semana(semana),
        "tema": tema,
        "proporcion": comparacion["proporcion"],
        "promedio": comparacion["promedio"],
        "s_max": comparacion["s_max"],
        "h": comparacion["h"],
        "negativas": comparacion["negativas"],
        "total": comparacion["total"],
        "k": comparacion["semanas_historial"],
        "ejemplos": repo.ejemplos_negativos(semana, tema, 2),
        "tipo": tipo,
    }
    enviado = notificador.enviar(alerta, ahora.isoformat())
    alerta.update(enviada_en=ahora.isoformat(), mensaje=enviado["mensaje"])
    repo.guardar_alerta(alerta)
    if repo.semana(semana) is not None:
        repo.marcar_alerta_semana(semana)
        repo.con.commit()
    return alerta


def construir_reporte(
    repo: RepositorioHistorico,
    reportes: GeneradorReporte,
    semana: int,
    ahora: datetime,
    incompleto: bool,
    cfg: dict,
    nota: str = "",
) -> Path:
    """Genera siempre un reporte determinista usando solo SQLite."""
    conteos = repo.conteos_semana(semana)
    comp = comparar_temas(repo, semana, cfg)
    alertas = [a for a in repo.alertas() if a["semana"] == semana]
    rev = repo.con.execute(
        "SELECT COUNT(*) FROM resenas WHERE semana = ? AND revision_manual = 1", (semana,)
    ).fetchone()[0]
    ruta = reportes.generar(
        semana, texto_semana(semana), conteos, comp, alertas,
        incompleto, int(rev), ahora.isoformat(), nota=nota,
    )
    repo.guardar_reporte(semana, ahora.isoformat(), str(ruta), incompleto)
    return ruta


# La herramienta pública es un adaptador del análisis determinista existente.
from pydantic import BaseModel, ConfigDict, Field
from .registro import Contexto, ErrorHerramienta, herramienta


class Comparar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semana: int = Field(ge=0)
    tema: str | None = None


@herramienta("comparar_semana", "Calcula CUSUM y señales de alarma por semana y tema.", Comparar)
def comparar_semana(entrada: Comparar, ctx: Contexto) -> dict:
    from .resenas import _existe_semana
    if not _existe_semana(ctx, entrada.semana):
        raise ErrorHerramienta("sin_datos", "No hay datos para esa semana.")
    if entrada.tema is not None and entrada.tema not in TEMAS:
        raise ErrorHerramienta("argumentos_invalidos", "Tema no reconocido.")
    resultados = comparar_temas(ctx.repo, entrada.semana, ctx.cfg)
    if entrada.tema is not None:
        resultados = {entrada.tema: resultados[entrada.tema]}
    for tema, comparacion in resultados.items():
        if comparacion["alarma"]:
            clave = (entrada.semana, tema)
            ctx.sesion.comparaciones_positivas.add(clave)
            ctx.sesion.comparaciones[clave] = dict(comparacion)
    return resultados
