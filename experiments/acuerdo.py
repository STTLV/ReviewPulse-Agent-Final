"""Acuerdo interevaluador y consolidación responsable del conjunto gold."""
from __future__ import annotations

from collections import Counter
import csv
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
POLARIDADES = {"positiva", "negativa", "neutra"}
TEMAS = {"limpieza", "servicio", "ubicacion", "precio"}


def cohen_kappa(a: list[str], b: list[str]) -> float:
    """Kappa de Cohen sin dependencias; ambas listas deben estar alineadas."""
    if not a or len(a) != len(b):
        raise ValueError("Se requieren listas alineadas y no vacías.")
    n = len(a)
    observado = sum(x == y for x, y in zip(a, b)) / n
    frecuencia_a, frecuencia_b = Counter(a), Counter(b)
    esperado = sum(frecuencia_a[x] * frecuencia_b[x] for x in set(a) | set(b)) / (n * n)
    if abs(1.0 - esperado) < 1e-12:
        return 1.0 if observado == 1.0 else 0.0
    return (observado - esperado) / (1.0 - esperado)


def leer_csv(ruta: Path, columnas: list[str]) -> list[dict[str, str]]:
    with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        if lector.fieldnames != columnas:
            raise ValueError(f"Columnas incorrectas en {ruta}: {lector.fieldnames}")
        filas = list(lector)
    ids = [fila["id"] for fila in filas]
    if any(not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError(f"IDs vacíos o duplicados en {ruta}")
    return filas


def consolidar_gold(raiz: Path = RAIZ) -> dict:
    raiz = Path(raiz)
    carpeta = raiz / "data" / "gold"
    muestra = leer_csv(carpeta / "muestra.csv", ["id", "texto"])
    sara = leer_csv(carpeta / "etiquetas_sara.csv", ["id", "texto", "polaridad", "tema"])
    ellen = leer_csv(carpeta / "etiquetas_ellen.csv", ["id", "texto", "polaridad", "tema"])
    if len(muestra) != 120 or len(sara) != 66 or len(ellen) != 66:
        raise ValueError("Reparto inválido: muestra=120; Sara=66; Ellen=66.")
    ids = [r["id"] for r in muestra]
    if set(r["id"] for r in sara) != set(ids[:66]):
        raise ValueError("Los IDs asignados a Sara no cumplen 12+54.")
    if set(r["id"] for r in ellen) != (set(ids[:12]) | set(ids[66:])):
        raise ValueError("Los IDs asignados a Ellen no cumplen 12+54.")
    por_id = {r["id"]: r for r in muestra}
    pendientes = []
    for nombre, filas in (("Sara", sara), ("Ellen", ellen)):
        for fila in filas:
            if fila["texto"] != por_id[fila["id"]]["texto"]:
                raise ValueError(f"El texto se modificó: {nombre}, {fila['id']}")
            if not fila["polaridad"].strip() or not fila["tema"].strip():
                pendientes.append(f"{nombre}:{fila['id']}")
            elif fila["polaridad"] not in POLARIDADES or fila["tema"] not in TEMAS:
                raise ValueError(f"Etiqueta inválida: {nombre}, {fila['id']}")
    if pendientes:
        raise RuntimeError(f"Faltan {len(pendientes)} etiquetas humanas completas; ejemplos: {', '.join(pendientes[:6])}. No se creó gold.csv.")
    s, e = ({r["id"]: r for r in filas} for filas in (sara, ellen))
    comunes = ids[:12]
    k_polaridad = cohen_kappa([s[i]["polaridad"] for i in comunes], [e[i]["polaridad"] for i in comunes])
    k_tema = cohen_kappa([s[i]["tema"] for i in comunes], [e[i]["tema"] for i in comunes])
    diferencias = [i for i in comunes if s[i]["polaridad"] != e[i]["polaridad"] or s[i]["tema"] != e[i]["tema"]]
    resoluciones = {}
    if diferencias:
        ruta = carpeta / "acuerdos_resueltos.csv"
        if not ruta.exists():
            with ruta.open("w", encoding="utf-8", newline="") as archivo:
                w = csv.DictWriter(archivo, fieldnames=["id", "polaridad", "tema", "justificacion"], lineterminator="\n")
                w.writeheader()
            raise RuntimeError(f"Hay {len(diferencias)} desacuerdos en los 12 comunes. Conversen, completen {ruta} y vuelvan a ejecutar.")
        resoluciones = {r["id"]: r for r in leer_csv(ruta, ["id", "polaridad", "tema", "justificacion"])}
        if set(resoluciones) != set(diferencias) or any(
            r["polaridad"] not in POLARIDADES or r["tema"] not in TEMAS or not r["justificacion"].strip()
            for r in resoluciones.values()
        ):
            raise RuntimeError("Resoluciones incompletas o inválidas; no se creó gold.csv.")
    finales = []
    for fila in muestra:
        i = fila["id"]
        etiqueta = resoluciones[i] if i in resoluciones else (s[i] if i in s else e[i])
        finales.append({"id": i, "texto": fila["texto"], "polaridad": etiqueta["polaridad"], "tema": etiqueta["tema"]})
    destino = carpeta / "gold.csv"
    # No sobrescribir una versión ya consolidada con contenidos diferentes.
    if destino.exists():
        anterior = leer_csv(destino, ["id", "texto", "polaridad", "tema"])
        if anterior != finales:
            raise RuntimeError("gold.csv ya existe y es distinto. Revisar manualmente; no se sobrescribió.")
    else:
        with destino.open("w", encoding="utf-8", newline="") as archivo:
            w = csv.DictWriter(archivo, fieldnames=["id", "texto", "polaridad", "tema"], lineterminator="\n")
            w.writeheader()
            w.writerows(finales)
    return {"total": len(finales), "comunes": 12, "desacuerdos": len(diferencias), "kappa_polaridad": k_polaridad, "kappa_tema": k_tema, "ruta": destino}


if __name__ == "__main__":
    try:
        resumen = consolidar_gold()
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        print("ETIQUETADO PENDIENTE:", e)
        raise SystemExit(1) from e
    print(f"Kappa polaridad (12 comunes): {resumen['kappa_polaridad']:.4f}")
    print(f"Kappa tema (12 comunes): {resumen['kappa_tema']:.4f}")
    print(f"Desacuerdos resueltos: {resumen['desacuerdos']}")
    print(f"Conjunto gold consolidado: {resumen['ruta']} ({resumen['total']} reseñas)")
