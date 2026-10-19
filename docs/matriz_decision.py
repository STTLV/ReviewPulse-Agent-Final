"""Matriz de decisión ponderada (Fase 1) y análisis de sensibilidad. Reproducible.

Uso: python docs/matriz_decision.py
"""
import json
from pathlib import Path

CRITERIOS = [  # (criterio, peso, ReviewPulse, RetainIQ)
    ("Viabilidad técnica", 0.25, 4, 3),
    ("Disponibilidad de datos o entorno", 0.20, 4, 3),
    ("Medibilidad del desempeño", 0.20, 5, 3),
    ("Complejidad de IA", 0.15, 3, 5),
    ("Costo y recursos", 0.10, 5, 5),
    ("Valor del problema", 0.10, 3, 4),
]


def puntaje(pesos, idx):
    return sum(w * c[idx] for w, c in zip(pesos, CRITERIOS))


def mover_peso(i, delta):
    """Suma `delta` al criterio i y reparte la diferencia entre los demás en proporción a su peso."""
    pesos = [c[1] for c in CRITERIOS]
    resto = 1 - pesos[i]
    nuevo = pesos[i] + delta
    return [nuevo if j == i else w * (1 - nuevo) / resto for j, w in enumerate(pesos)]


def main():
    pesos = [c[1] for c in CRITERIOS]
    assert abs(sum(pesos) - 1) < 1e-9
    base = {"ReviewPulse": puntaje(pesos, 2), "RetainIQ": puntaje(pesos, 3)}
    influencia = [(c[0], abs(c[1] * (c[2] - c[3]))) for c in CRITERIOS]
    mas_influyente = max(range(len(CRITERIOS)), key=lambda i: influencia[i][1])
    sens = []
    for i in range(len(CRITERIOS)):
        for d in (+0.10, -0.10):
            p = mover_peso(i, d)
            a, b = puntaje(p, 2), puntaje(p, 3)
            sens.append({"criterio": CRITERIOS[i][0], "cambio": f"{d:+.0%}", "peso_nuevo": round(p[i], 2),
                         "ReviewPulse": round(a, 3), "RetainIQ": round(b, 3),
                         "ganador": "ReviewPulse" if a > b else "RetainIQ"})
    r = {"puntajes": {k: round(v, 3) for k, v in base.items()},
         "influencia": [(n, round(v, 3)) for n, v in influencia],
         "criterio_mas_influyente": CRITERIOS[mas_influyente][0], "sensibilidad": sens}
    Path(__file__).with_name("matriz_decision.json").write_text(json.dumps(r, ensure_ascii=False, indent=2),
                                                               encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
