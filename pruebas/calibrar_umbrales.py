"""Calibra los parámetros de decisión del agente con semillas de CALIBRACIÓN (101–105).

Las semillas de prueba (11–55) no se usan aquí, para no ajustar el agente con los
mismos datos con que se califica. Criterio: maximizar la detección de incidentes
relevantes en escenarios normales y límite manteniendo los falsos positivos por
debajo de 8 % (margen frente al umbral de 10 % de M4).

Uso:
  python pruebas/recolectar_estadisticas.py 101,102,103,104,105 salidas/calibracion/estadisticas.json
  python pruebas/calibrar_umbrales.py
"""
import csv
import itertools
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CAL = RAIZ / "salidas" / "calibracion"
REJILLA = {
    "alfa": [0.005, 0.01, 0.02, 0.04, 0.08],
    "delta_minimo": [0.05, 0.10, 0.15, 0.20, 0.25],
    "min_negativas": [3, 4, 5, 6],
    "z_minimo": [0.0, 1.5, 2.0, 2.5, 3.0],
    "min_semanas_historial": [3, 4],
}


def alerta(f, p):
    return (f["semanas_historial"] >= p["min_semanas_historial"] and f["p_valor"] < p["alfa"] / 4
            and f["proporcion"] - f["promedio"] >= p["delta_minimo"] and f["negativas"] >= p["min_negativas"]
            and f["z"] >= p["z_minimo"])


def evaluar(filas, p):
    g = [f for f in filas if f["tipo"] != "falla"]
    rel = [f for f in g if f["verdad"] == "relevante"]
    al = [f for f in g if alerta(f, p)]
    fp = [f for f in al if f["verdad"] != "relevante"]
    return {"deteccion": sum(alerta(f, p) for f in rel) / len(rel), "alertas": len(al), "fp": len(fp),
            "tasa_fp": len(fp) / len(al) if al else 0.0}


def main():
    filas = json.loads((CAL / "estadisticas.json").read_text(encoding="utf-8"))
    res = []
    for v in itertools.product(*REJILLA.values()):
        p = dict(zip(REJILLA, v))
        res.append({**p, **evaluar(filas, p)})
    validas = [r for r in res if r["tasa_fp"] < 0.08]
    mejor = max(validas, key=lambda r: (round(r["deteccion"], 3), -r["tasa_fp"], r["z_minimo"], r["alfa"] * -1))
    with (CAL / "calibracion.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0]))
        w.writeheader()
        w.writerows(res)
    (CAL / "elegido.json").write_text(json.dumps(mejor, indent=2), encoding="utf-8")
    print(f"{len(res)} combinaciones evaluadas; {len(validas)} con FP < 8 %")
    print("Elegido:", mejor)
    for r in sorted(validas, key=lambda r: -r["deteccion"])[:8]:
        print(r)


if __name__ == "__main__":
    main()
