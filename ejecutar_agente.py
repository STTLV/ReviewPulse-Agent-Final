"""Ejecuta el agente desde cero en un escenario y deja el log, la memoria y los reportes.

Uso: python ejecutar_agente.py --escenario E02 --semilla 11
"""
import argparse
import json
import shutil
from pathlib import Path

from reviewpulse.agente import ReviewPulseAgent
from reviewpulse.entorno import EntornoHotel
from reviewpulse.escenarios import ESCENARIOS
from reviewpulse.evaluacion import evaluar_corrida

ap = argparse.ArgumentParser()
ap.add_argument("--escenario", default="E02", choices=list(ESCENARIOS))
ap.add_argument("--semilla", type=int, default=11)
ap.add_argument("--config", default="config/config.json")
a = ap.parse_args()

carpeta = Path("salidas") / "demo" / f"{a.escenario}_s{a.semilla}"
shutil.rmtree(carpeta, ignore_errors=True)
entorno = EntornoHotel(ESCENARIOS[a.escenario], a.semilla)
cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
print(f"Escenario: {ESCENARIOS[a.escenario].nombre} — {ESCENARIOS[a.escenario].descripcion}")
agente = ReviewPulseAgent(entorno, carpeta, cfg)
resultado = agente.ejecutar()
for al in resultado["alertas"]:
    print("ALERTA:", al["mensaje"][:160], "…")
m = evaluar_corrida(entorno, resultado)
print(json.dumps({k: v for k, v in m.items() if k != "fp_detalle"}, indent=2, ensure_ascii=False))
print(f"Log: {carpeta / 'log_ejecucion.jsonl'} · Reportes: {carpeta / 'reportes'}")
