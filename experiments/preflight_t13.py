"""T13: auditoría de planificación completamente offline.

NO importa ClienteOpenAI, NO acepta credenciales y NO permite ejecutar modelos.
La salida `estado` informa el estado documental, NO constituye autorización.
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
SISTEMAS = ("agente", "base")
REPETICIONES = (1, 2, 3)
TIPOS = {"conteo": 3, "comparacion": 3, "evidencia": 3,
         "clasificacion": 3, "alerta": 3, "reporte": 1, "trampa": 4}


def cargar_catalogo(ruta: Path) -> list[dict[str, Any]]:
    # PyYAML es una dependencia existente del proyecto.
    import yaml
    tareas = yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))
    if not isinstance(tareas, list) or Counter(
            t.get("tipo") for t in tareas if isinstance(t, dict)) != TIPOS:
        raise ValueError("El catálogo no tiene la distribución fija de 20 tareas.")
    ids = [t.get("id") for t in tareas]
    if (len(ids) != 20 or any(not isinstance(i, str) or not i for i in ids)
            or len(set(ids)) != 20):
        raise ValueError("El catálogo tiene IDs de tareas inválidos o repetidos.")
    if any(not isinstance(t, dict) for t in tareas):
        raise ValueError("El catálogo contiene tareas inválidas.")
    return tareas



def leer_campos_runner(ruta: Path) -> list[str]:
    """Extrae el esquema con AST; nunca importa ni ejecuta el runner real."""
    arbol = ast.parse(Path(ruta).read_text(encoding="utf-8"), filename=str(ruta))
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "CAMPOS" for t in nodo.targets):
            campos = ast.literal_eval(nodo.value)
            if (isinstance(campos, list) and len(campos) == len(set(campos))
                    and all(isinstance(s, str) and s for s in campos)
                    and all(s in campos for s in ("sistema", "tarea", "tipo", "repeticion",
                                                   "tokens_juez_entrada", "tokens_total_entrada"))):
                return campos
    raise ValueError("No se pudo verificar el esquema CAMPOS del runner.")

def construir_plan(tareas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"sistema": s, "tarea": t["id"], "tipo": t["tipo"], "repeticion": r,
             "necesita_juez": t["tipo"] == "reporte"}
            for s in SISTEMAS for t in tareas for r in REPETICIONES]


def inspeccionar_csv(ruta: Path | None, plan: list[dict], campos: list[str]) -> dict:
    """Solo lectura. Rechaza columnas viejas, duplicados y claves ajenas."""
    if ruta is None:
        return {"archivo": None, "filas": 0, "pendientes": len(plan),
                "estado": "sin_csv_suministrado"}
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ValueError("El CSV indicado no existe. No se crea ni modifica.")
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        if lector.fieldnames != campos:
            raise ValueError("Esquema CSV antiguo o incompatible. No reutilizarlo.")
        filas = list(lector)
    esperado = {(p["sistema"], p["tarea"], p["repeticion"]): p["tipo"] for p in plan}
    vistas = set()
    for f in filas:
        try:
            rep = int(f["repeticion"])
            k = (f["sistema"], f["tarea"], rep)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("CSV con clave incompleta o inválida.") from exc
        if k not in esperado or f.get("tipo") != esperado[k]:
            raise ValueError("CSV contiene tarea/sistema/repetición ajena al plan.")
        if k in vistas:
            raise ValueError("CSV contiene una corrida duplicada.")
        vistas.add(k)
    return {"archivo": str(ruta), "filas": len(filas),
            "pendientes": len(plan) - len(vistas),
            "estado": "sin_cobertura_total" if len(vistas) < len(plan) else "120_claves_presentes_no_validadas"}


def reporte_previo(tareas: list[dict], umbrales: dict,
                    resultado_csv: dict) -> dict:
    if (umbrales.get("tareas") != 20 or umbrales.get("repeticiones") != 3
            or umbrales.get("sistemas") != ["agente", "base"]):
        raise ValueError("Los umbrales no corresponden al plan fijo.")
    plan = construir_plan(tareas)
    if len(plan) != 120 or len({(p["sistema"], p["tarea"], p["repeticion"])
                                for p in plan}) != 120:
        raise ValueError("La matriz experimental no es válida.")
    return {
        "estado": "PREPARACION_OFFLINE_SIN_AUTORIZACION_DE_GASTO",
        "version": "t13-preflight-v1",
        "no_realiza_llamadas": True,
        "autoriza_ejecucion_real": False,
        "matriz": {"tareas": 20, "repeticiones": 3, "sistemas": 2,
                   "total": 120, "agente": 60, "linea_base": 60,
                   "dictamenes_juez_previstos": sum(p["necesita_juez"] for p in plan)},
        "tipo_tareas": dict(Counter(t["tipo"] for t in tareas)),
        "csv": resultado_csv,
        "umbral_historico_usd": umbrales.get("costo_usd_max_evaluacion"),
        "no_confundir_umbral_con_presupuesto_aprobado": True,
        "bloqueantes": [
            "Falta confirmar los IDs efectivos y tarifas de las variantes provistas por OmniRoute.",
            "Falta autorización expresa del presupuesto máximo real de las 120 corridas.",
            "Falta evidencia verificable de un límite efectivo en la cuenta del proveedor.",
            "Falta prueba de recuperación ante fallos y control de reintentos con dobles sin red.",
        ],
        "advertencia": (
            "LLM_TOPE_TOKENS_DIA positivo NO es un límite monetario efectivo. "
            "--limite-ejecuciones limita casos, NO llamadas HTTP, reintentos ni gasto. "
            "El SDK puede cobrar solicitudes cuyos tokens no se registren si fallan."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tareas", type=Path, default=RAIZ / "experiments/tareas.yaml")
    ap.add_argument("--umbrales", type=Path, default=RAIZ / "experiments/umbrales.json")
    ap.add_argument("--csv", type=Path, help="Solo lectura. No crea ni reanuda corridas.")
    ap.add_argument("--runner", type=Path, default=RAIZ / "experiments/correr.py", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        tareas = cargar_catalogo(args.tareas)
        umbrales = json.loads(args.umbrales.read_text(encoding="utf-8"))
        if not isinstance(umbrales, dict):
            raise ValueError("Los umbrales deben ser un objeto JSON.")
        # Lee solo el AST del runner: no importa clientes, llaves ni SDK.
        CAMPOS = leer_campos_runner(args.runner)
        plan = construir_plan(tareas)
        csv_estado = inspeccionar_csv(args.csv, plan, CAMPOS)
        rep = reporte_previo(tareas, umbrales, csv_estado)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        ap.error(str(exc))
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
