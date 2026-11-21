"""Prepara una muestra ciega reproducible, sin exponer la verdad del simulador."""
from __future__ import annotations

import csv
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

from reviewpulse.corpus import construir_corpus  # noqa: E402

COLUMNAS_MUESTRA = ["id", "texto"]
COLUMNAS_ETIQUETAS = ["id", "texto", "polaridad", "tema"]
COLUMNAS_SIMULADOR = ["id", "polaridad", "tema", "ironia"]


def escribir_si_seguro(ruta: Path, cabeceras: list[str], filas: list[dict]) -> None:
    """No modifica archivos con contenido diferente, incluyendo etiquetas humanas."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists():
        with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
            actual = csv.DictReader(archivo)
            if actual.fieldnames != cabeceras or list(actual) != filas:
                raise RuntimeError(f"El archivo ya existe con datos diferentes: {ruta}. No se sobrescribe.")
        return
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=cabeceras, lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(filas)


def preparar_gold(raiz: Path = RAIZ, reserva: Path | None = None) -> dict[str, Path]:
    """Crea 120 reseñas, dos plantillas 12+54 y la verdad FUERA del repositorio."""
    raiz = Path(raiz)
    carpeta = raiz / "data" / "gold"
    reserva = Path(reserva) if reserva is not None else Path.home() / ".reviewpulse" / "verdad_simulador_2026.csv"
    if reserva.resolve().is_relative_to(raiz.resolve()):
        raise ValueError("La verdad del simulador debe guardarse fuera del repositorio.")

    generadas = construir_corpus(120, semilla=2026, conjunto="evaluacion", prob_ironia=0.10)
    if len(generadas) != 120:
        raise RuntimeError("El generador no produjo las 120 reseñas previstas.")
    muestra = [{"id": f"EVAL-{i:03d}", "texto": x["texto"]} for i, x in enumerate(generadas, 1)]
    if len({r["id"] for r in muestra}) != 120 or len({r["texto"] for r in muestra}) != 120:
        raise RuntimeError("Se detectaron registros repetidos.")

    para_sara = muestra[:66]              # 12 en común + 54 exclusivos
    para_ellen = muestra[:12] + muestra[66:]  # 12 en común + 54 exclusivos

    def vacias(registros: list[dict]) -> list[dict]:
        return [{**r, "polaridad": "", "tema": ""} for r in registros]

    rutas = {
        "muestra": carpeta / "muestra.csv",
        "sara": carpeta / "etiquetas_sara.csv",
        "ellen": carpeta / "etiquetas_ellen.csv",
        "verdad_reservada": reserva,
    }
    # Validar todos los destinos ANTES de escribir alguno.
    tareas = [
        (rutas["muestra"], COLUMNAS_MUESTRA, muestra),
        (rutas["sara"], COLUMNAS_ETIQUETAS, vacias(para_sara)),
        (rutas["ellen"], COLUMNAS_ETIQUETAS, vacias(para_ellen)),
        (reserva, COLUMNAS_SIMULADOR, [
            {"id": r["id"], "polaridad": x["polaridad"], "tema": x["tema"], "ironia": str(bool(x["ironia"])).lower()}
            for r, x in zip(muestra, generadas)
        ]),
    ]
    for ruta, campos, filas in tareas:
        if ruta.exists():
            with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
                lector = csv.DictReader(archivo)
                if lector.fieldnames != campos or list(lector) != filas:
                    # No exigir que las plantillas sean vacías cuando ya han sido etiquetadas:
                    # validar el contenido de la muestra y las columnas, sin borrar etiquetas.
                    if ruta in (rutas["sara"], rutas["ellen"]):
                        with ruta.open("r", encoding="utf-8-sig", newline="") as fuente:
                            lectura = csv.DictReader(fuente)
                            actual = list(lectura)
                            if lectura.fieldnames == campos and len(actual) == len(filas) and all(
                                a["id"] == e["id"] and a["texto"] == e["texto"] for a, e in zip(actual, filas)
                            ):
                                continue
                    raise RuntimeError(f"Conflicto: {ruta}; no se modificó ningún archivo.")

    for ruta, campos, filas in tareas:
        if ruta.exists():
            continue
        escribir_si_seguro(ruta, campos, filas)
    return rutas


if __name__ == "__main__":
    resultado = preparar_gold()
    print("Muestra ciega: 120 registros; Sara: 66; Ellen: 66; 12 comunes.")
    print("Plantillas sin etiquetas: no se generó gold.csv.")
    print("Verdad del simulador conservada fuera del repositorio:", resultado["verdad_reservada"])
    print("No abrir la verdad reservada hasta terminar el etiquetado humano.")
