"""Tarea 9: agente ReAct vs. línea base de una llamada, mismo modelo.

Por seguridad NUNCA invoca un servicio remoto sin --ejecutar-real. Registra
sólo resultados minimizados y trazas redactadas; no guarda prompts completos,
reseñas individuales, claves ni respuestas textuales sin filtrar.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from reviewpulse.actuadores import GeneradorReporte, Notificador
from reviewpulse.agente.bucle import resolver, cifras_sin_respaldo
from reviewpulse.agente.traza import Traza, _seguro
from reviewpulse.config import cargar_ajustes
from reviewpulse.ciclo.ingesta import CONFIG_DEFECTO
from reviewpulse.entorno import EntornoHotel, inicio_semana
from reviewpulse.escenarios import ESCENARIOS
from reviewpulse.herramientas.registro import Contexto, Sesion
from reviewpulse.llm.cliente import ClienteLLM, ClienteOpenAI
from reviewpulse.memoria import RepositorioHistorico
from reviewpulse.modelo import ClasificadorSentimiento

try:
    from experiments.preparar import preparar_base
    from experiments.verdad import cargar_tareas, cifras_incorrectas, prompt_linea_base, pregunta_completa, valores_esperados, verificar
    from experiments.juez import evaluar_reporte
except ModuleNotFoundError:
    # Permite invocar 'python experiments/correr.py' desde la raíz.
    from preparar import preparar_base
    from verdad import cargar_tareas, cifras_incorrectas, prompt_linea_base, pregunta_completa, valores_esperados, verificar
    from juez import evaluar_reporte

RAIZ = Path(__file__).resolve().parents[1]
CAMPOS = ["sistema", "tarea", "tipo", "repeticion", "estado", "exito", "tokens_entrada",
          "tokens_salida", "segundos", "pasos", "herramientas", "errores_herramienta",
          "cifras_no_respaldadas", "motivo", "veredicto_juez"]


def _comprobar_umbrales_fijados() -> None:
    ruta = "experiments/umbrales.json"
    try:
        commit = subprocess.run(["git", "log", "-1", "--format=%H", "--", ruta],
                                cwd=RAIZ, capture_output=True, text=True, check=True)
        estado = subprocess.run(["git", "status", "--porcelain", "--", ruta],
                                cwd=RAIZ, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("No se pudo comprobar el commit de umbrales.") from exc
    if not commit.stdout.strip() or estado.stdout.strip():
        raise RuntimeError("Primero debes versionar sin cambios pendientes experiments/umbrales.json.")


def _ruta_datos(carpeta: Path, base: Path) -> tuple[Path, Path]:
    # DB de trabajo independiente por ejecución, para evitar que el agente
    # modifique los datos usados por ejecuciones posteriores.
    trabajo = carpeta / "sesion"
    trabajo.mkdir()
    copia = trabajo / "memoria.db"
    shutil.copy2(base, copia)
    return trabajo, copia


def _agente(pregunta: str, llm: ClienteLLM, copia: Path, carpeta: Path,
            modelo: Any) -> tuple[str, int, int, int, int, int, str, list[dict]]:
    repo = RepositorioHistorico(copia)
    traza = Traza(carpeta / "traza_agente.jsonl")
    try:
        ctx = Contexto(repo=repo, modelo=modelo,
                       entorno=EntornoHotel(ESCENARIOS["E03"], 11),
                       notificador=Notificador(carpeta, CONFIG_DEFECTO["destinatario"]),
                       reportes=GeneradorReporte(carpeta),
                       cfg={**CONFIG_DEFECTO}, ahora=inicio_semana(14) + timedelta(hours=12),
                       sesion=Sesion())
        resultado = resolver(pregunta, llm, ctx, traza=traza)
        herramientas = [e for e in resultado.eventos if e.get("evento") == "herramienta"]
        fallos = sum(1 for e in herramientas if (e.get("resultado") or {}).get("ok") is not True)
        return (resultado.texto, resultado.uso.entrada, resultado.uso.salida,
                resultado.pasos, len(herramientas), fallos, resultado.motivo,
                resultado.eventos)
    finally:
        repo.cerrar()


def _base(pregunta: str, llm: ClienteLLM, base: Path, modelo_nombre: str) -> tuple[str, int, int, int, int, int, str, list[dict]]:
    respuesta = llm.chat(prompt_linea_base(pregunta, base), herramientas=None,
                        modelo=modelo_nombre)
    return (respuesta.texto or "", respuesta.uso.entrada if respuesta.uso else 0,
            respuesta.uso.salida if respuesta.uso else 0, 1, 0, 0,
            "completado" if respuesta.ok else (respuesta.error or "proveedor"), [])


def ejecutar_una(tarea: dict, sistema: str, repeticion: int, base: Path,
                 cliente: ClienteLLM, modelo_nombre: str, juez_modelo: str,
                 carpeta_trazas: Path, clasificador: Any | None = None) -> dict:
    """Ejecuta un caso; permite dobles de prueba sin red."""
    if sistema not in {"agente", "base"}:
        raise ValueError("Sistema no reconocido.")
    if repeticion < 1:
        raise ValueError("Repetición inválida.")
    pregunta = pregunta_completa(tarea)
    tiempo = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="reviewpulse_t9_") as temporal:
        carpeta, copia = _ruta_datos(Path(temporal), base)
        if sistema == "agente":
            (texto, entrada, salida, pasos, herramientas, fallos,
             motivo, eventos) = _agente(pregunta, cliente, copia, carpeta,
                                       clasificador or ClasificadorSentimiento.cargar())
        else:
            (texto, entrada, salida, pasos, herramientas, fallos,
             motivo, eventos) = _base(pregunta, cliente, base, modelo_nombre)
        veredicto = None
        if tarea["tipo"] == "reporte" and motivo == "completado":
            veredicto = evaluar_reporte(cliente, juez_modelo, texto, base, tarea["semana"])
            entrada += int(veredicto.get("tokens_entrada", 0))
            salida += int(veredicto.get("tokens_salida", 0))
            exito = veredicto.get("veredicto")
        else:
            exito = verificar(tarea, texto, base) if motivo in {"completado", "cifra_sin_respaldo"} else False
        traza_salida = carpeta_trazas / f'{sistema}_{tarea["id"]}_r{repeticion}.jsonl'
        traza_salida.parent.mkdir(parents=True, exist_ok=True)
        # Sólo metadatos y trazas del agente filtradas; nunca guarda la respuesta
        # de texto completa ni mensajes del proveedor.
        with traza_salida.open("w", encoding="utf-8") as out:
            out.write(json.dumps({"sistema": sistema, "tarea": tarea["id"],
                                  "repeticion": repeticion, "motivo": motivo,
                                  "exito": exito,
                                  "juez": _seguro(veredicto) if veredicto else None},
                                 ensure_ascii=False) + "\n")
            for ev in eventos:
                out.write(json.dumps(_seguro(ev), ensure_ascii=False) + "\n")
        incorrectas = cifras_incorrectas(texto, valores_esperados(tarea, base)) if tarea["tipo"] == "conteo" else []
        return {"sistema": sistema, "tarea": tarea["id"], "tipo": tarea["tipo"],
                "repeticion": repeticion,
                "estado": "juez_pendiente" if exito is None else "terminado",
                "exito": "" if exito is None else int(bool(exito)),
                "tokens_entrada": entrada, "tokens_salida": salida,
                "segundos": round(time.monotonic() - tiempo, 3), "pasos": pasos,
                "herramientas": herramientas, "errores_herramienta": fallos,
                "cifras_no_respaldadas": len(incorrectas), "motivo": motivo,
                "veredicto_juez": "" if veredicto is None else json.dumps(_seguro(veredicto), ensure_ascii=False)}


def _leer_hechas(archivo: Path) -> set[tuple[str, str, int]]:
    if not archivo.exists():
        return set()
    with archivo.open(encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    # La reanudación omite todas las claves ya registradas. Los errores no se
    # reintentan automáticamente para evitar duplicados y gastos inesperados.
    return {(fila["sistema"], fila["tarea"], int(fila["repeticion"])) for fila in filas}


def ejecutar_lote(sistema: str, repeticiones: int, tareas_ids: list[str],
                  limite: int | None, base: Path, salida: Path,
                  cliente: ClienteLLM, modelo: str, juez_modelo: str) -> dict:
    tareas = cargar_tareas()
    desconocidas = set(tareas_ids) - {t["id"] for t in tareas}
    if desconocidas:
        raise ValueError(f"Tareas desconocidas: {sorted(desconocidas)}")
    seleccion = [t for t in tareas if not tareas_ids or t["id"] in tareas_ids]
    hechas = _leer_hechas(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    nuevas = 0
    with salida.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CAMPOS)
        if salida.stat().st_size == 0:
            writer.writeheader()
        for sistema_actual in (["agente", "base"] if sistema == "ambos" else [sistema]):
            for t in seleccion:
                for repeticion in range(1, repeticiones + 1):
                    clave = (sistema_actual, t["id"], repeticion)
                    if clave in hechas:
                        continue
                    if limite is not None and nuevas >= limite:
                        return {"ejecuciones_nuevas": nuevas, "limite_alcanzado": True}
                    fila = ejecutar_una(t, sistema_actual, repeticion, base, cliente,
                                        modelo, juez_modelo, salida.parent / "trazas")
                    writer.writerow(fila)
                    file.flush()
                    nuevas += 1
                    print(f'{sistema_actual} {t["id"]} repetición {repeticion}: {fila["estado"]}', flush=True)
    return {"ejecuciones_nuevas": nuevas, "limite_alcanzado": False}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sistema", choices=["agente", "base", "ambos"], default="ambos")
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--tareas", nargs="*", default=[])
    ap.add_argument("--limite-ejecuciones", type=int)
    ap.add_argument("--ejecutar-real", action="store_true", help="Autoriza llamadas y costos reales del proveedor")
    ap.add_argument("--base", type=Path, default=RAIZ / "experiments/resultados/base_t9")
    ap.add_argument("--salida", type=Path, default=RAIZ / "experiments/resultados/corridas.csv")
    args = ap.parse_args()
    if not args.ejecutar_real:
        print("MODO SEGURO: no se realizaron llamadas. Usa --ejecutar-real solo con autorización.")
        return 0
    if args.repeticiones < 1 or args.repeticiones > 3:
        raise SystemExit("Las repeticiones permitidas están entre 1 y 3.")
    if args.limite_ejecuciones is not None and args.limite_ejecuciones < 1:
        raise SystemExit("El límite debe ser positivo.")
    _comprobar_umbrales_fijados()
    ajustes = cargar_ajustes()
    if (not ajustes.llm_api_key or not ajustes.llm_base_url or
            not ajustes.llm_model or not ajustes.llm_juez_model or
            ajustes.llm_tope_tokens_dia < 1):
        raise SystemExit("Proveedor no configurado. No se ejecutó ninguna llamada.")
    if ajustes.llm_model == ajustes.llm_juez_model:
        raise SystemExit("El modelo juez debe ser distinto del agente y de la línea base.")
    base = preparar_base(args.base)
    resultado = ejecutar_lote(args.sistema, args.repeticiones, args.tareas,
                              args.limite_ejecuciones, base, args.salida,
                              ClienteOpenAI(ajustes), ajustes.llm_model, ajustes.llm_juez_model)
    print(json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
