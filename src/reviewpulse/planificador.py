"""Planificación orientada a metas (tipo STRIPS) con búsqueda en anchura.

El agente describe su situación con hechos booleanos y busca la secuencia más
corta de acciones cuyas precondiciones se cumplen y cuyos efectos alcanzan la
meta. Si no existe plan (por ejemplo, la semana cerró pero falta el margen de
espera o una plataforma está caída y aún hay tiempo), el agente decide esperar.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Accion:
    nombre: str
    pre: frozenset
    pre_neg: frozenset
    agrega: frozenset

    def aplicable(self, estado: frozenset) -> bool:
        return self.pre <= estado and not (self.pre_neg & estado)

    def aplicar(self, estado: frozenset) -> frozenset:
        return estado | self.agrega


def A(nombre, pre=(), pre_neg=(), agrega=()):
    return Accion(nombre, frozenset(pre), frozenset(pre_neg), frozenset(agrega))


ACCIONES = [
    A("limpiar_lote", pre=["lote_nuevo"], pre_neg=["limpio"], agrega=["limpio"]),
    A("clasificar_lote", pre=["limpio"], pre_neg=["clasificado"], agrega=["clasificado"]),
    A("actualizar_conteos", pre=["clasificado"], pre_neg=["conteos_al_dia"], agrega=["conteos_al_dia"]),
    A("comparar_historial", pre=["semana_cerrada", "conteos_al_dia", "puede_cerrar"], pre_neg=["comparado"],
      agrega=["comparado"]),
    A("decidir_alerta", pre=["comparado"], pre_neg=["decision_tomada"], agrega=["decision_tomada"]),
    A("generar_reporte", pre=["decision_tomada"], pre_neg=["reporte_entregado"], agrega=["reporte_entregado"]),
    A("registrar_historial", pre=["reporte_entregado"], pre_neg=["registrado"], agrega=["registrado"]),
    A("reevaluar_semanas_tardias", pre=["hay_tardias", "conteos_al_dia"], pre_neg=["tardias_revisadas"],
      agrega=["tardias_revisadas"]),
]

METAS = {
    "mantener_conteos_al_dia": frozenset({"conteos_al_dia"}),
    "entregar_resumen_semanal": frozenset({"decision_tomada", "reporte_entregado", "registrado"}),
    "revisar_semanas_cerradas": frozenset({"tardias_revisadas"}),
}


def planificar(estado: frozenset, meta: frozenset, acciones=ACCIONES, max_prof: int = 12):
    """BFS sobre estados simbólicos. Devuelve la lista de nombres de acción, [] o None."""
    if meta <= estado:
        return []
    frontera, vistos = deque([(estado, [])]), {estado}
    while frontera:
        s, plan = frontera.popleft()
        if len(plan) >= max_prof:
            continue
        for a in acciones:
            if a.aplicable(s):
                s2 = a.aplicar(s)
                if s2 in vistos:
                    continue
                if meta <= s2:
                    return plan + [a.nombre]
                vistos.add(s2)
                frontera.append((s2, plan + [a.nombre]))
    return None
