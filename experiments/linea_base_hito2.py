"""Hito 2: línea base mayoritaria frente al modelo de ReviewPulse.

Ambos métodos se evalúan SOBRE LAS MISMAS 40 reseñas de control.
La clase mayoritaria se aprende solo del conjunto de entrenamiento sintético.
El modelo propuesto se carga del archivo congelado `data/modelo.joblib`.
Este resultado es UNA ejecución del modelo guardado, no el promedio M1
que se obtuvo con cinco reentrenamientos (81 % y 90 % respectivamente).

Ejecutar desde la raíz del repositorio:
    python -m experiments.linea_base_hito2
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from sklearn.metrics import f1_score  # noqa: E402
from reviewpulse.corpus import construir_corpus  # noqa: E402
from reviewpulse.modelo import ClasificadorSentimiento, RUTA_MODELO  # noqa: E402


def calcular() -> tuple[dict, list[dict]]:
    if not RUTA_MODELO.exists():
        raise FileNotFoundError(
            "Falta data/modelo.joblib; no se reentrena para conservar la comparación."
        )
    entrenamiento = construir_corpus(
        4000, semilla=7, conjunto="entrenamiento", prob_ironia=0.10
    )
    with (RAIZ / "data" / "evaluacion_manual_holdout.csv").open(
        encoding="utf-8-sig", newline=""
    ) as f:
        control = list(csv.DictReader(f))
    if len(control) != 40:
        raise ValueError(f"Se esperaban 40 reseñas de control; llegaron {len(control)}")
    if any(not r.get("texto") or not r.get("polaridad") or not r.get("tema") for r in control):
        raise ValueError("El conjunto de control contiene entradas incompletas")

    mayorias = {c: Counter(r[c] for r in entrenamiento).most_common(1)[0][0]
                 for c in ("polaridad", "tema")}
    modelo = ClasificadorSentimiento.cargar(RUTA_MODELO)
    pred = modelo.predecir([r["texto"] for r in control])
    if len(pred) != len(control):
        raise AssertionError("El clasificador no produjo una respuesta por reseña")

    detalle = []
    for r, p in zip(control, pred):
        detalle.append({
            "id": r["id"],
            "polaridad_real": r["polaridad"],
            "polaridad_mayoritaria": mayorias["polaridad"],
            "polaridad_reviewpulse": p.polaridad,
            "tema_real": r["tema"],
            "tema_mayoritario": mayorias["tema"],
            "tema_reviewpulse": p.tema,
        })

    resultados = {
        "titulo": "Hito 2 - Comparación de línea base contra ReviewPulse",
        "conjunto": "data/evaluacion_manual_holdout.csv",
        "origen": "Corpus sintético; conjunto manual asistido por IA, no reseñas reales",
        "n_control": len(control),
        "entrenamiento_base": {"n": len(entrenamiento), "semilla": 7,
                                 "conjunto": "frases de entrenamiento"},
        "modelo": "data/modelo.joblib (modelo congelado, sin reentrenar)",
        "nota": "No equivale a M1 histórica (media de cinco reentrenamientos); ambas "
                "técnicas se comparan aquí en el mismo control y una sola ejecución.",
        "metricas": {},
    }
    for campo in ("polaridad", "tema"):
        reales = [r[campo] for r in control]
        base = [mayorias[campo]] * len(control)
        actual = [getattr(p, campo) for p in pred]
        nb = sum(a == b for a, b in zip(reales, base))
        nm = sum(a == b for a, b in zip(reales, actual))
        resultados["metricas"][campo] = {
            "clase_mayoritaria": mayorias[campo],
            "linea_base": {"aciertos": nb, "n": len(control),
                           "exactitud": round(nb/len(control),4),
                           "f1_macro": round(float(f1_score(reales,base,average="macro",zero_division=0)),4)},
            "reviewpulse": {"aciertos": nm, "n": len(control),
                            "exactitud": round(nm/len(control),4),
                            "f1_macro": round(float(f1_score(reales,actual,average="macro",zero_division=0)),4)},
            "mejora_puntos_porcentuales": round(100*(nm-nb)/len(control),1),
        }
    return resultados, detalle


def main() -> None:
    resultados, detalle = calcular()
    ruta_resumen = RAIZ / "experiments" / "v1" / "linea_base_hito2.json"
    ruta_detalle = RAIZ / "experiments" / "v1" / "comparacion_holdout.csv"
    ruta_resumen.parent.mkdir(parents=True, exist_ok=True)
    ruta_detalle.parent.mkdir(parents=True, exist_ok=True)
    ruta_resumen.write_text(json.dumps(resultados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with ruta_detalle.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(detalle[0]))
        escritor.writeheader()
        escritor.writerows(detalle)
    for campo, v in resultados["metricas"].items():
        b,m=v["linea_base"],v["reviewpulse"]
        print(f"{campo}: línea base {b['aciertos']}/40 = {b['exactitud']:.0%}; "
              f"ReviewPulse {m['aciertos']}/40 = {m['exactitud']:.0%}; "
              f"mejora {v['mejora_puntos_porcentuales']:+.1f} pp")
    print("Resumen: experiments/v1/linea_base_hito2.json")
    print("Detalle: experiments/v1/comparacion_holdout.csv")


if __name__ == "__main__":
    main()
