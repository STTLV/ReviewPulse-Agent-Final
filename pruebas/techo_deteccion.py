"""Análisis de causa de M2: ¿cuánto falla por el clasificador y cuánto por el volumen de datos?

Aplica la misma regla de alerta del agente a las etiquetas REALES del simulador
(clasificador perfecto) y a volúmenes mayores, con las semillas de prueba.
No usa el agente ni el modelo; solo el entorno y la función de decisión.

Uso: python pruebas/techo_deteccion.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from reviewpulse.agente import CONFIG_DEFECTO, cola_binomial  # noqa: E402
from reviewpulse.corpus import TEMAS  # noqa: E402
from reviewpulse.entorno import EntornoHotel  # noqa: E402
from reviewpulse.escenarios import ESCENARIOS  # noqa: E402

SEMILLAS = json.loads((RAIZ / "pruebas" / "umbrales.json").read_text(encoding="utf-8"))["semillas"]


def evaluar(esc, semilla, cfg, factor_volumen=1.0):
    import copy
    e = copy.deepcopy(esc)
    e.volumen_base *= factor_volumen
    env = EntornoHotel(e, semilla)
    conteo = defaultdict(lambda: {t: {"negativa": 0, "total": 0} for t in TEMAS})
    for r in env.resenas:
        if r["polaridad"] is None:
            continue
        c = conteo[r["semana_real"]][r["tema"]]
        c["total"] += 1
        c["negativa"] += r["polaridad"] == "negativa"
    inc = det = alertas = fp = 0
    alertadas = set()
    for s in range(e.semanas):
        hist = [h for h in range(max(0, s - 12), s) if h not in alertadas][-cfg["semanas_historial"]:]
        for t in TEMAS:
            c = conteo[s][t]
            relevante = env.verdad[s]["incidentes"].get(t) == "relevante"
            inc += relevante
            props = [conteo[h][t]["negativa"] / conteo[h][t]["total"] for h in hist if conteo[h][t]["total"]]
            if len(hist) < cfg["min_semanas_historial"] or not props or not c["total"]:
                continue
            prom = sum(props) / len(props)
            base = (sum(conteo[h][t]["negativa"] for h in hist) + 1) / (sum(conteo[h][t]["total"] for h in hist) + 4)
            p = cola_binomial(c["negativa"], c["total"], base)
            prop = c["negativa"] / c["total"]
            if p < cfg["alfa"] / 4 and prop - prom >= cfg["delta_minimo"] and c["negativa"] >= cfg["min_negativas"]:
                alertas += 1
                alertadas.add(s)
                det += relevante
                fp += not relevante
    return inc, det, alertas, fp


def main():
    cfg = dict(CONFIG_DEFECTO)
    filas = []
    for nombre, filtro in [("todos", lambda e: True), ("sin fallas de plataforma ni arranque en frío",
                                                      lambda e: e.tipo != "falla")]:
        for factor in (1.0, 2.0, 3.0):
            tot = [0, 0, 0, 0]
            for eid, esc in ESCENARIOS.items():
                if not filtro(esc) or eid == "E11":  # E11: sin datos al cierre, no aplica
                    continue
                for s in SEMILLAS:
                    tot = [a + b for a, b in zip(tot, evaluar(esc, s, cfg, factor))]
            inc, det, al, fp = tot
            filas.append({"conjunto": nombre, "volumen": f"x{factor:g}", "incidentes": inc, "detectados": det,
                          "deteccion": round(det / inc, 3), "alertas": al, "fp": fp,
                          "tasa_fp": round(fp / al, 3) if al else 0.0})
            print(filas[-1])
    (RAIZ / "salidas" / "pruebas" / "techo_deteccion.json").write_text(json.dumps(filas, indent=2, ensure_ascii=False),
                                                                     encoding="utf-8")


if __name__ == "__main__":
    main()
