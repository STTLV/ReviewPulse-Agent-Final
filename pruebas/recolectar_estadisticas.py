"""Corre cada escenario una vez y guarda, por semana y tema, las estadísticas que usa la regla de alerta.

Sirve para calibrar los parámetros de decisión fuera de línea (pruebas/calibrar_umbrales.py)
sin repetir la clasificación de miles de reseñas por cada combinación de parámetros.

Uso: python pruebas/recolectar_estadisticas.py 101,102,103,104,105 salidas/calibracion/estadisticas.json
"""
import json
import sys
import tempfile
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

warnings.filterwarnings("ignore")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from reviewpulse.agente import ReviewPulseAgent  # noqa: E402
from reviewpulse.entorno import EntornoHotel  # noqa: E402
from reviewpulse.escenarios import ESCENARIOS  # noqa: E402
from reviewpulse.modelo import ClasificadorSentimiento  # noqa: E402

CAMPOS = ["negativas", "total", "proporcion", "promedio", "desviacion", "z", "p_valor", "semanas_historial"]


def correr(args):
    eid, semilla = args
    modelo = ClasificadorSentimiento.cargar()
    with tempfile.TemporaryDirectory() as d:
        env = EntornoHotel(ESCENARIOS[eid], semilla)
        # parámetros permisivos: se registran todas las comparaciones sin filtrar
        ag = ReviewPulseAgent(env, Path(d), {"alfa": 4.0, "delta_minimo": -1, "min_negativas": 0,
                                             "z_minimo": -99, "min_semanas_historial": 0}, modelo)
        original = ag.repo.historial
        ag.repo.historial = lambda antes, k, excluir_alertadas=True: original(antes, k, False)
        ag._emitir_alerta = lambda s, t, c, ahora, tipo: {"tema": t, "mensaje": ""}
        ag.ejecutar()
        filas = []
        for e in ag.log.eventos:
            if e["evento"] == "comparacion_historial":
                for t, c in e["comparacion"].items():
                    filas.append({"escenario": eid, "semilla": semilla, "semana": e["semana"], "tema": t,
                                  "tipo": ESCENARIOS[eid].tipo,
                                  "verdad": env.verdad[e["semana"]]["incidentes"].get(t, "ninguno"),
                                  **{k: c[k] for k in CAMPOS}})
        return filas


if __name__ == "__main__":
    semillas = [int(x) for x in sys.argv[1].split(",")]
    salida = Path(sys.argv[2])
    salida.parent.mkdir(parents=True, exist_ok=True)
    tareas = [(e, s) for e in ESCENARIOS for s in semillas]
    with ProcessPoolExecutor(2) as ex:
        filas = [f for r in ex.map(correr, tareas) for f in r]
    salida.write_text(json.dumps(filas), encoding="utf-8")
    print(len(filas), "comparaciones guardadas en", salida)
