"""Simulador del entorno: un hotel piloto y sus plataformas de reseñas.

Respeta las propiedades de ambiente de la sección 3 del diseño:
- Parcialmente observable: el estado operativo real del hotel (calidad por tema
  cada semana) está oculto; el agente solo ve el texto y los metadatos.
- Estocástico: volumen de reseñas Poisson, polaridad y tema aleatorios,
  ironía, ruido de escritura, retrasos de publicación y caídas de plataforma.
- Secuencial: las semanas se encadenan y el agente compara contra su historial.
- Dinámico: las reseñas siguen apareciendo mientras el agente procesa; una
  reseña publicada el domingo puede volverse visible el lunes.
- Discreto: reseñas contables, categorías cerradas, cortes semanales.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .corpus import (ENTRADAS_INVALIDAS, OTROS_IDIOMAS, TEMAS, calificacion_para, generar_resena)

INICIO = datetime(2026, 1, 5)  # lunes
PLATAFORMAS = ["TripAdvisor", "Google"]


class PlataformaNoDisponible(Exception):
    """El conector no pudo leer la plataforma (caída, cuota agotada, cambio de API)."""


@dataclass
class Incidente:
    semana: int
    tema: str
    severidad: str  # "relevante" (debe alertar) o "leve" (variación normal, no debe alertar)
    prob_negativa: float
    peso_tema: float = 1.0


@dataclass
class Caida:
    plataforma: str  # "TripAdvisor", "Google" o "todas"
    desde: datetime
    hasta: datetime


@dataclass
class Escenario:
    nombre: str
    descripcion: str
    tipo: str  # normal, limite, falla
    semanas: int = 14
    volumen_base: float = 36.0
    multiplicador_volumen: dict = field(default_factory=dict)  # semana -> factor
    incidentes: list = field(default_factory=list)
    caidas: list = field(default_factory=list)
    prob_otro_idioma: float = 0.03
    prob_invalida: float = 0.02
    prob_ironia: float = 0.05
    retraso_medio_h: float = 4.0
    conjunto_frases: str = "mezcla"  # 50 % frases que el modelo no vio al entrenar


def inicio_semana(semana: int) -> datetime:
    return INICIO + timedelta(weeks=semana)


def semana_de(fecha: datetime) -> int:
    return (fecha - INICIO).days // 7


def _poisson(rng: random.Random, lam: float) -> int:
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


class EntornoHotel:
    """Genera el flujo de reseñas y expone conectores por plataforma."""

    PROB_NEG_BASE, PROB_NEU_BASE = 0.20, 0.25

    def __init__(self, escenario: Escenario, semilla: int):
        self.escenario = escenario
        self.rng = random.Random(semilla)
        self.resenas: list[dict] = []
        self.verdad: dict[int, dict] = {}  # oculto para el agente; solo lo usan las pruebas
        self._generar()

    def _generar(self):
        esc, rng = self.escenario, self.rng
        contador = 0
        for s in range(esc.semanas):
            incid = {i.tema: i for i in esc.incidentes if i.semana == s}
            pesos = [incid[t].peso_tema if t in incid else 1.0 for t in TEMAS]
            n = _poisson(rng, esc.volumen_base * esc.multiplicador_volumen.get(s, 1.0))
            self.verdad[s] = {"incidentes": {t: i.severidad for t, i in incid.items()}, "n_generadas": n}
            for _ in range(n):
                contador += 1
                fecha = inicio_semana(s) + timedelta(seconds=rng.uniform(0, 7 * 86400 - 1))
                visible = fecha + timedelta(hours=min(rng.expovariate(1 / esc.retraso_medio_h), 30))
                plataforma = rng.choices(PLATAFORMAS, weights=[0.55, 0.45])[0]
                tema = rng.choices(TEMAS, weights=pesos)[0]
                p_neg = incid[tema].prob_negativa if tema in incid else self.PROB_NEG_BASE
                p_neu = self.PROB_NEU_BASE * (1 - p_neg) / (1 - self.PROB_NEG_BASE)
                pol = rng.choices(["negativa", "neutra", "positiva"], weights=[p_neg, p_neu, 1 - p_neg - p_neu])[0]
                r = generar_resena(rng, tema, pol, conjunto=esc.conjunto_frases, prob_ironia=esc.prob_ironia)
                r.update({"id": f"R{contador:05d}", "plataforma": plataforma, "fecha": fecha.isoformat(),
                          "visible_desde": visible, "semana_real": s, "calificacion": None})
                if plataforma == "Google" or rng.random() < 0.85:
                    r["calificacion"] = calificacion_para(rng, pol)
                u = rng.random()
                if u < esc.prob_otro_idioma:
                    r.update(texto=rng.choice(OTROS_IDIOMAS), polaridad=None, tema=None)
                elif u < esc.prob_otro_idioma + esc.prob_invalida:
                    r.update(texto=rng.choice(ENTRADAS_INVALIDAS), polaridad=None, tema=None)
                    if rng.random() < 0.3:
                        r["fecha"] = None
                self.resenas.append(r)
        self.resenas.sort(key=lambda r: r["visible_desde"])

    def disponible(self, plataforma: str, ahora: datetime) -> bool:
        return not any(c.desde <= ahora < c.hasta and c.plataforma in (plataforma, "todas")
                       for c in self.escenario.caidas)

    def consultar(self, plataforma: str, desde: datetime, ahora: datetime) -> list[dict]:
        """API del conector: reseñas visibles en (desde, ahora]. Sin etiquetas verdaderas."""
        if not self.disponible(plataforma, ahora):
            raise PlataformaNoDisponible(f"{plataforma} no responde a las {ahora:%Y-%m-%d %H:%M}")
        visibles = [r for r in self.resenas
                    if r["plataforma"] == plataforma and desde < r["visible_desde"] <= ahora]
        return [{k: r[k] for k in ("id", "plataforma", "fecha", "texto", "calificacion")} for r in visibles]

    def etiqueta_real(self, id_resena: str) -> dict:
        r = next(x for x in self.resenas if x["id"] == id_resena)
        return {"tema": r["tema"], "polaridad": r["polaridad"], "ironia": r.get("ironia", False)}
