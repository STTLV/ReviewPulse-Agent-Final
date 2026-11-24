"""M1–M4 sin red. Requiere calibración fijada y COMMIT previo.

M1 se informa sobre C03, como en el plan. Gold manual y comparación con LLM
sin ajuste se marcan pendientes hasta que existan datos reales y presupuesto.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / 'src') not in sys.path:
    sys.path.insert(0, str(RAIZ / 'src'))

from reviewpulse.agente.bucle import ManejadorAgente
from reviewpulse.ciclo.cierre import ejecutar_simulacion
from reviewpulse.corpus import construir_corpus
from reviewpulse.entorno import EntornoHotel
from reviewpulse.escenarios import ESCENARIOS
from reviewpulse.evaluacion import evaluar_corrida
from reviewpulse.herramientas.registro import Contexto, Sesion
from reviewpulse.llm.falso import LLMFalso, guion_operativo
from reviewpulse.modelo import ClasificadorSentimiento

SEMILLAS_PRUEBA = (11, 22, 33, 44, 55)
SEMILLAS_REENTRENAMIENTO = (71, 72, 73, 74, 75)
COLUMNAS = ('regla', 'escenario', 'semilla', 'detectados_24h', 'incidentes',
            'alertas', 'fp', 'reportes_a_tiempo')


def _git(*args: str) -> str:
    r = subprocess.run(['git', *args], cwd=RAIZ, capture_output=True,
                       text=True, encoding='utf-8')
    if r.returncode:
        raise RuntimeError(f'No se pudo verificar la fijación de parámetros: {r.stderr.strip()}')
    return r.stdout.strip()


def verificar_calibracion_fijada() -> dict:
    """Evita medir con parámetros que aún no constan en un commit."""
    if not (RAIZ / 'experiments/calibracion_fijada.json').exists():
        raise RuntimeError('No hay calibración fijada. Ejecuta calibrar_cusum.py primero.')
    # El archivo debe formar parte de HEAD y su contenido ser idéntico.
    versionado = _git('show', 'HEAD:experiments/calibracion_fijada.json')
    local = (RAIZ / 'experiments/calibracion_fijada.json').read_text(encoding='utf-8')
    if json.loads(versionado) != json.loads(local):
        raise RuntimeError('Calibración modificada sin commit.')
    if _git('diff', '--name-only', 'HEAD', '--', 'config/config.json'):
        raise RuntimeError('config/config.json tiene cambios no guardados.')
    cfg = json.loads((RAIZ / 'config/config.json').read_text(encoding='utf-8-sig'))
    eleccion = json.loads(local)['eleccion']
    for k, campo in [('cusum_delta', 'delta'), ('cusum_h', 'h'),
                     ('cusum_min_negativas', 'min_negativas')]:
        if float(cfg[k]) != float(eleccion[campo]):
            raise RuntimeError(f'{k} no coincide con la calibración fijada.')
    return cfg


def medir_corridas(cfg: dict, codigos=None, semillas=None, modelo=None) -> list[dict]:
    """Corre el ciclo completo, usando el agente con LLM falso sin red."""
    codigos = tuple(codigos or sorted(ESCENARIOS))
    semillas = tuple(semillas or SEMILLAS_PRUEBA)
    modelo = modelo or ClasificadorSentimiento.cargar()
    filas = []
    for codigo in codigos:
        if codigo not in ESCENARIOS:
            raise ValueError(f'Escenario no reconocido: {codigo}')
        for semilla in semillas:
            entorno = EntornoHotel(ESCENARIOS[codigo], semilla)
            with tempfile.TemporaryDirectory(prefix='reviewpulse-m2m4-') as carpeta:
                # LLMFalso de Tarea 4 consume un guion iterable. Se suministra
                # una secuencia amplia de la MISMA función operativa, sin red.
                llm = LLMFalso([guion_operativo] * 2000)

                def fabrica(repo, notificador, reportes, configuracion):
                    def contexto(ahora):
                        return Contexto(repo, modelo, entorno, notificador,
                                        reportes, configuracion, ahora, Sesion())
                    return ManejadorAgente(llm, contexto)

                salida = ejecutar_simulacion(entorno, Path(carpeta), cfg=cfg,
                                            modelo=modelo, fabrica_manejador=fabrica)
                medidas = evaluar_corrida(entorno, salida)
            filas.append({
                'regla': 'cusum', 'escenario': codigo, 'semilla': semilla,
                'detectados_24h': medidas['detectados_24h'],
                'incidentes': medidas['incidentes_relevantes'],
                'alertas': medidas['alertas_total'],
                'fp': medidas['alertas_fp'],
                'reportes_a_tiempo': medidas['reportes_a_tiempo'],
            })
            print(f"{codigo} semilla {semilla}: detección {medidas['detectados_24h']}/"
                  f"{medidas['incidentes_relevantes']} FP={medidas['alertas_fp']} "
                  f"reportes={medidas['reportes_a_tiempo']}", flush=True)
    return filas


def cargar_v1() -> list[dict]:
    """Conserva los valores históricos, sin reinterpretarlos como corridas nuevas."""
    with (RAIZ / 'experiments/v1/escenarios.csv').open(encoding='utf-8-sig', newline='') as f:
        filas = list(csv.DictReader(f))
    if len(filas) != 60:
        raise ValueError('El histórico v1 debe contener 60 corridas.')
    return [{
        'regla': 'semanal_v1', 'escenario': r['escenario'], 'semilla': int(r['semilla']),
        'detectados_24h': int(r['detectados_24h']),
        'incidentes': int(r['incidentes_relevantes']),
        'alertas': int(r['alertas_total']),
        'fp': int(r['alertas_fp']),
        'reportes_a_tiempo': int(r['reportes_a_tiempo']),
    } for r in filas]


def resumir(filas: list[dict]) -> dict:
    if not filas:
        raise ValueError('No hay corridas para resumir.')
    incidentes = sum(int(f['incidentes']) for f in filas)
    detectados = sum(int(f['detectados_24h']) for f in filas)
    alertas = sum(int(f['alertas']) for f in filas)
    fp = sum(int(f['fp']) for f in filas)
    reportes = sum(int(f['reportes_a_tiempo']) for f in filas)
    esperados = 14 * len(filas)
    m2 = detectados / incidentes if incidentes else None
    m3 = reportes / esperados
    m4 = fp / alertas if alertas else 0.0
    return {'corridas': len(filas), 'incidentes': incidentes, 'detectados_24h': detectados,
            'alertas': alertas, 'fp': fp, 'reportes_a_tiempo': reportes,
            'semanas_esperadas': esperados, 'M2': m2, 'M3': m3, 'M4': m4,
            'cumple_M2': m2 is not None and m2 >= 0.90,
            'cumple_M3': m3 == 1.0,
            'cumple_M4': m4 < 0.10}


def medir_m1_c03() -> dict:
    """Cinco reentrenamientos sobre entrenamiento, evaluación C03 sin fuga."""
    from sklearn.metrics import f1_score
    ruta = RAIZ / 'data/evaluacion_manual_holdout.csv'
    with ruta.open(encoding='utf-8-sig', newline='') as f:
        control = list(csv.DictReader(f))
    if len(control) != 40 or any(not r.get('texto') or not r.get('polaridad') or not r.get('tema') for r in control):
        raise ValueError('El holdout C03 está incompleto.')
    textos = [r['texto'] for r in control]
    exactitud = {'polaridad': [], 'tema': []}
    f1 = {'polaridad': [], 'tema': []}
    for semilla in SEMILLAS_REENTRENAMIENTO:
        corpus = construir_corpus(4000, semilla=semilla, conjunto='entrenamiento', prob_ironia=0.10)
        modelo = ClasificadorSentimiento().entrenar(corpus)  # nunca guardar sobre modelo.joblib
        preds = modelo.predecir(textos)
        for campo in ('polaridad', 'tema'):
            reales = [r[campo] for r in control]
            pronosticos = [getattr(p, campo) for p in preds]
            exactitud[campo].append(sum(a == b for a,b in zip(reales, pronosticos)) / len(control))
            f1[campo].append(float(f1_score(reales, pronosticos, average='macro', zero_division=0)))
    return {'conjunto': 'C03: data/evaluacion_manual_holdout.csv',
            'semillas_entrenamiento': list(SEMILLAS_REENTRENAMIENTO),
            'n': len(control),
            'procedencia': 'Conjunto de control histórico manual asistido por IA; gold de Tarea 7 pendiente',
            'exactitud': {campo: sum(v)/len(v) for campo,v in exactitud.items()},
            'f1_macro': {campo: sum(v)/len(v) for campo,v in f1.items()},
            'cumple_m1': all(sum(v)/len(v) >= 0.85 for v in exactitud.values()),
            'gold_manual': 'pendiente hasta terminar etiquetado humano',
            'comparacion_llm_sin_ajuste': 'pendiente; no se invocó proveedor'}


def guardar(filas: list[dict], m1: dict) -> dict:
    destino = RAIZ / 'experiments/resultados/m1_m4.csv'
    resumen_ruta = RAIZ / 'experiments/resultados/resumen_m1_m4.json'
    if destino.exists() or resumen_ruta.exists():
        raise FileExistsError('Ya hay resultados; no se sobrescribieron.')
    base = cargar_v1()
    if len(filas) != 60 or {(r['escenario'], int(r['semilla'])) for r in filas} != {
        (codigo, semilla) for codigo in ESCENARIOS for semilla in SEMILLAS_PRUEBA
    }:
        raise ValueError('Se requieren las 60 corridas E01..E12 × semillas de prueba.')
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS, lineterminator='\n')
        w.writeheader(); w.writerows(base + filas)
    resumen = {'umbrales_invariables': {'M1_polaridad': .85, 'M1_tema': .85,
                                       'M2': .90, 'M3': 1.0, 'M4_max_exclusivo': .10},
               'm1': m1, 'v1': resumir(base), 'cusum': resumir(filas),
               'origen': {'v1': 'experiments/v1/escenarios.csv',
                          'cusum': 'ciclo real con LLMFalso de guion, sin red'},
               'estado': 'provisional: gold manual y comparacion LLM pendiente'}
    resumen_ruta.write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return resumen


def main():
    cfg = verificar_calibracion_fijada()
    filas = medir_corridas(cfg)
    m1 = medir_m1_c03()
    resumen = guardar(filas, m1)
    for version in ('v1', 'cusum'):
        r = resumen[version]
        print(f"{version}: M2={r['M2']!s} (cumple={r['cumple_M2']}), "
              f"M3={r['M3']:.1%} (cumple={r['cumple_M3']}), "
              f"M4={r['M4']:.1%} (cumple={r['cumple_M4']})")
    print('M1 C03:', resumen['m1']['exactitud'], 'cumple:', resumen['m1']['cumple_m1'])
    print('Gold humano y comparación LLM sin ajuste: PENDIENTES')


if __name__ == '__main__':
    main()
