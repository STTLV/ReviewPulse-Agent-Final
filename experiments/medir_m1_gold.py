"""Evaluación adicional de M1 contra el Gold humano T7, sin red ni reescrituras.

Conserva los resultados históricos C03 y los parámetros CUSUM existentes.
Ejecución desde experiments/medir_m1_gold.py en una copia aislada del repositorio.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

SEMILLAS_REENTRENAMIENTO = (71, 72, 73, 74, 75)
POLARIDADES = {"positiva", "negativa", "neutra"}
TEMAS = {"limpieza", "servicio", "ubicacion", "precio"}


def leer_gold(raiz: Path = RAIZ) -> list[dict[str, str]]:
    """Valida Gold definitivo y su correspondencia con la muestra ciega."""
    carpeta = raiz / "data" / "gold"
    ruta_gold = carpeta / "gold.csv"
    ruta_muestra = carpeta / "muestra.csv"
    with ruta_gold.open("r", encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        if lector.fieldnames != ["id", "texto", "polaridad", "tema"]:
            raise ValueError("Gold no tiene columnas id,texto,polaridad,tema.")
        gold = list(lector)
    with ruta_muestra.open("r", encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        if lector.fieldnames != ["id", "texto"]:
            raise ValueError("La muestra no tiene columnas id,texto.")
        muestra = list(lector)
    if len(gold) != 120 or len(muestra) != 120:
        raise ValueError("Se necesitan exactamente 120 reseñas de Gold y muestra.")
    ids = [f"EVAL-{i:03d}" for i in range(1, 121)]
    if [f['id'] for f in gold] != ids or [f['id'] for f in muestra] != ids:
        raise ValueError("Los IDs deben ser únicos y estar ordenados EVAL-001..EVAL-120.")
    for g, m in zip(gold, muestra):
        if not g['texto'].strip() or g['texto'] != m['texto']:
            raise ValueError(f"El texto de {g['id']} no coincide con la muestra.")
        if g['polaridad'] not in POLARIDADES or g['tema'] not in TEMAS:
            raise ValueError(f"Etiqueta faltante o inválida en {g['id']}.")
    return gold


def evaluar_gold(gold: list[dict[str, str]]) -> dict:
    """Cinco reentrenamientos sobre entrenamiento; Gold usado SOLO para prueba."""
    from sklearn.metrics import f1_score
    from reviewpulse.corpus import construir_corpus
    from reviewpulse.modelo import ClasificadorSentimiento

    textos = [r['texto'] for r in gold]
    ejecuciones = []
    for semilla in SEMILLAS_REENTRENAMIENTO:
        corpus = construir_corpus(4000, semilla=semilla,
                                  conjunto='entrenamiento', prob_ironia=0.10)
        modelo = ClasificadorSentimiento().entrenar(corpus)
        predicciones = modelo.predecir(textos)
        if len(predicciones) != len(gold):
            raise RuntimeError(f"Semilla {semilla}: cantidad incorrecta de predicciones.")
        exactitud = {}
        f1_macro = {}
        for campo in ('polaridad', 'tema'):
            reales = [r[campo] for r in gold]
            estimadas = [getattr(p, campo) for p in predicciones]
            exactitud[campo] = sum(a == b for a, b in zip(reales, estimadas)) / len(gold)
            f1_macro[campo] = float(f1_score(reales, estimadas, average='macro', zero_division=0))
        ejecuciones.append({'semilla': semilla, 'exactitud': exactitud, 'f1_macro': f1_macro})
        print(f"Semilla {semilla}: exactitud polaridad={exactitud['polaridad']:.3f}, "
              f"tema={exactitud['tema']:.3f}", flush=True)

    promedio = {
        metrica: {campo: sum(f[metrica][campo] for f in ejecuciones) / len(ejecuciones)
                  for campo in ('polaridad', 'tema')}
        for metrica in ('exactitud', 'f1_macro')
    }
    return {
        'tipo': 'evaluacion_adicional_gold_humano_T7',
        'conjunto': 'data/gold/gold.csv',
        'n': len(gold),
        'semillas_reentrenamiento': list(SEMILLAS_REENTRENAMIENTO),
        'modelo': 'TF-IDF + regresion logistica',
        'fuente_entrenamiento': 'construir_corpus(4000, conjunto=entrenamiento, prob_ironia=0.10)',
        'umbral_m1': 0.85,
        'resultados_por_semilla': ejecuciones,
        'promedios': promedio,
        'cumple_m1': all(promedio['exactitud'][x] >= 0.85 for x in ('polaridad', 'tema')),
        'limitaciones': [
            'Las 120 reseñas son sintéticas, con patrones compartidos con el generador.',
            'El Gold se utiliza exclusivamente para medir, no para entrenar ni calibrar.',
            'Esta evaluación complementa M1-C03 histórico, no lo sustituye.',
            'No se comparó con un proveedor LLM real en esta ejecución.'
        ]
    }


def main() -> None:
    ruta = RAIZ / 'experiments' / 'resultados' / 'm1_gold.json'
    if ruta.exists():
        raise FileExistsError(f"El resultado ya existe: {ruta}. No se sobrescribe.")
    gold = leer_gold()
    resultado = evaluar_gold(gold)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # Exclusivo: si surge otro archivo mientras corre, no lo sobrescribimos.
    with ruta.open('x', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('Resultado guardado en:', ruta)
    print('Cumple M1 Gold:', resultado['cumple_m1'])


if __name__ == '__main__':
    main()
