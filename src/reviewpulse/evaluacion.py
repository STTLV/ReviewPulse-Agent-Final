"""Cálculo de las medidas de desempeño a partir del resultado y la verdad del simulador.

La verdad del simulador (incidentes y etiquetas reales) nunca la ve el agente;
solo se usa aquí, después de la ejecución, para calificarlo.
"""
from __future__ import annotations

from datetime import datetime

from .entorno import EntornoHotel, inicio_semana


def horas_desde_cierre(semana: int, ts: str) -> float:
    return (datetime.fromisoformat(ts) - inicio_semana(semana + 1)).total_seconds() / 3600


def evaluar_corrida(entorno: EntornoHotel, resultado: dict, plazo_h: float = 24.0) -> dict:
    relevantes = {(s, t) for s, v in entorno.verdad.items() for t, sev in v["incidentes"].items()
                  if sev == "relevante"}
    alertas = resultado["alertas"]
    clave = lambda a: (a["semana"], a["tema"])
    lat = {clave(a): horas_desde_cierre(a["semana"], a["enviada_en"]) for a in alertas}
    a_tiempo = {k for k in relevantes if k in lat and lat[k] <= plazo_h}
    tardias = {k for k in relevantes if k in lat and lat[k] > plazo_h}
    vp = [a for a in alertas if clave(a) in relevantes]
    fp = [a for a in alertas if clave(a) not in relevantes]

    semanas = entorno.escenario.semanas
    rep = {r["semana"]: horas_desde_cierre(r["semana"], r["generado_en"]) for r in resultado["reportes"]}
    reportes_a_tiempo = sum(1 for s in range(semanas) if s in rep and rep[s] <= plazo_h)

    etiquetadas = resultado["resenas"]
    ok_pol = ok_tema = 0
    for r in etiquetadas:
        real = entorno.etiqueta_real(r["id"])
        ok_pol += real["polaridad"] == r["polaridad"]
        ok_tema += real["tema"] == r["tema"]
    n = max(len(etiquetadas), 1)
    return {
        "incidentes_relevantes": len(relevantes),
        "detectados_24h": len(a_tiempo),
        "detectados_tarde": len(tardias),
        "latencia_media_h": (sum(lat[k] for k in a_tiempo) / len(a_tiempo)) if a_tiempo else None,
        "alertas_total": len(alertas),
        "alertas_vp": len(vp),
        "alertas_fp": len(fp),
        "fp_detalle": [f"s{a['semana']}-{a['tema']}" for a in fp],
        "semanas_cerradas": semanas,
        "reportes_a_tiempo": reportes_a_tiempo,
        "latencia_reporte_max_h": max(rep.values()) if rep else None,
        "reportes_incompletos": sum(r["incompleto"] for r in resultado["reportes"]),
        "resenas_clasificadas": len(etiquetadas),
        "resenas_descartadas": len(resultado["descartadas"]),
        "exactitud_polaridad_flujo": ok_pol / n,
        "exactitud_tema_flujo": ok_tema / n,
        "revision_manual": sum(r["revision_manual"] for r in etiquetadas),
    }
