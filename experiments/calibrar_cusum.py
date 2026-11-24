"""Calibración honesta de CUSUM: usa solo semillas 101..105 y E01..E08.

Los escenarios sin fallos permiten reproducir el orden exacto de ingesta,
alertas y cierre sobre eventos clasificados, evitando 2400 escrituras SQLite.
La paridad del recálculo rápido se verifica en tests/test_medidas.py.
NO consulta semillas 11,22,33,44,55 ni las etiquetas gold.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / 'src') not in sys.path:
    sys.path.insert(0, str(RAIZ / 'src'))

from reviewpulse.corpus import TEMAS
from reviewpulse.entorno import INICIO, EntornoHotel, inicio_semana
from reviewpulse.escenarios import ESCENARIOS
from reviewpulse.herramientas.estadistica import ParamsCusum, cusum_diario, p0_suavizado
from reviewpulse.modelo import ClasificadorSentimiento
from reviewpulse.preprocesamiento import validar

SEMILLAS_CALIBRACION = (101, 102, 103, 104, 105)
ESCENARIOS_CALIBRACION = tuple(f'E{i:02d}' for i in range(1, 9))
DELTA = (0.15, 0.20, 0.25, 0.30)
HS = (2, 3, 4, 5, 6)
MIN_NEGATIVAS = (3, 4, 6)
COLUMNAS = ('delta', 'h', 'min_negativas', 'deteccion', 'tasa_fp',
            'detectados_24h', 'incidentes', 'fp', 'alertas')


def elegir_parametros(filas: list[dict], fp_max: float = 0.08) -> dict:
    """Prioriza detección con tasa FP estrictamente MENOR al límite.

    Si ninguna alternativa cumple, elige menor FP y marca la excepción.
    """
    if not filas or not (0 < fp_max < 1):
        raise ValueError('Se requieren resultados y un fp_max entre 0 y 1.')
    for fila in filas:
        for clave in ('h', 'deteccion', 'tasa_fp'):
            if clave not in fila or not math.isfinite(float(fila[clave])):
                raise ValueError(f'Valor de calibración inválido: {clave}')
        if not 0 <= float(fila['deteccion']) <= 1 or not 0 <= float(fila['tasa_fp']) <= 1:
            raise ValueError('Tasas fuera de [0,1].')
    aptas = [f for f in filas if float(f['tasa_fp']) < fp_max]
    # Desempate determinista: menor FP, h más alto y menor delta.
    if aptas:
        ganadora = min(aptas, key=lambda f: (-float(f['deteccion']),
                        float(f['tasa_fp']), -float(f['h']), float(f.get('delta', 0)),
                        -float(f.get('min_negativas', 0))))
    else:
        ganadora = min(filas, key=lambda f: (float(f['tasa_fp']),
                       -float(f['deteccion']), -float(f['h'])))
    return {**ganadora, 'cumple_fp_calibracion': bool(aptas), 'fp_max': fp_max}


def _vacio():
    return {tema: {polaridad: 0.0 for polaridad in ('negativa', 'neutra', 'positiva')}
            for tema in TEMAS}


def _clonar_conteos(conteos):
    return {tema: dict(valores) for tema, valores in conteos.items()}


def _momento_ingesta(visible: datetime, intervalo_h: int = 6) -> datetime:
    segundos = (visible - INICIO).total_seconds()
    n = max(1, math.ceil(segundos / (intervalo_h * 3600)))
    return INICIO + timedelta(hours=intervalo_h * n)


def preparar_caso(codigo: str, semilla: int, modelo: ClasificadorSentimiento) -> dict:
    """Predice cada reseña UNA sola vez y construye el calendario observable.

    Se limita a escenarios sin caídas de plataforma durante calibración.
    """
    if codigo not in ESCENARIOS_CALIBRACION or semilla not in SEMILLAS_CALIBRACION:
        raise ValueError('Calibración exclusiva: E01..E08 y semillas 101..105.')
    entorno = EntornoHotel(ESCENARIOS[codigo], semilla)
    if entorno.escenario.caidas:
        raise ValueError('El recálculo rápido no admite caídas de plataforma.')
    validas = []
    for r in entorno.resenas:
        correcto, texto, _ = validar(r)
        if correcto:
            validas.append((r, texto))
    predicciones = modelo.predecir([texto for _, texto in validas])
    if len(predicciones) != len(validas):
        raise RuntimeError('Número de predicciones inválido.')
    eventos: dict[datetime, list[tuple]] = defaultdict(list)
    fin = inicio_semana(entorno.escenario.semanas) + timedelta(hours=48)
    for (r, _), p in zip(validas, predicciones):
        ts = _momento_ingesta(r['visible_desde'])
        if ts > fin:
            continue
        semana = (datetime.fromisoformat(r['fecha']) - INICIO).days // 7
        dia = datetime.fromisoformat(r['fecha']).weekday()
        peso = 0.5 if p.confianza < 0.55 else 1.0
        eventos[ts].append((semana, dia, p.tema, p.polaridad, peso))
    cierres: dict[datetime, list[int]] = defaultdict(list)
    for semana in range(entorno.escenario.semanas):
        cierres[inicio_semana(semana + 1) + timedelta(hours=12)].append(semana)
    relevantes = {(semana, tema) for semana, datos in entorno.verdad.items()
                  for tema, gravedad in datos['incidentes'].items()
                  if gravedad == 'relevante'}
    return {'codigo': codigo, 'semilla': semilla, 'eventos': dict(eventos),
            'cierres': dict(cierres), 'relevantes': relevantes}


def evaluar_parametros_caso(caso: dict, delta: float, h: float,
                           min_negativas: int) -> dict:
    """Reproduce la evaluación CUSUM después de cada ingesta y cierre.

    Las semanas con alerta se excluyen del historial, como en SQLite.
    Los conteos por semana se actualizan incluso tras cierres tardíos.
    """
    params = ParamsCusum(delta, h, min_negativas)
    conteos = defaultdict(_vacio)
    diarios = defaultdict(lambda: {t: [[0.0, 0.0] for _ in range(7)] for t in TEMAS})
    cerradas: dict[int, dict] = {}
    alertas: dict[tuple[int, str], datetime] = {}
    calendario = sorted(set(caso['eventos']) | set(caso['cierres']))

    def comprobar(semana: int, ahora: datetime):
        historico = [s for s in sorted(cerradas, reverse=True)
                     if s < semana and not cerradas[s]['alerto']][:6]
        if len(historico) < 3:
            return
        for tema in TEMAS:
            clave = (semana, tema)
            if clave in alertas:
                continue
            total = sum(conteos[semana][tema].values())
            if total <= 0:
                continue
            nh = sum(cerradas[s]['conteos'][tema]['negativa'] for s in historico)
            nt = sum(sum(cerradas[s]['conteos'][tema].values()) for s in historico)
            p0 = p0_suavizado(nh, nt)
            serie = [tuple(x) for x in diarios[semana][tema]]
            if cusum_diario(serie, p0, params).alarma:
                alertas[clave] = ahora
                if semana in cerradas:
                    cerradas[semana]['alerto'] = True

    for ahora in calendario:
        afectadas = set()
        for semana, dia, tema, polaridad, peso in caso['eventos'].get(ahora, ()):
            conteos[semana][tema][polaridad] += peso
            diarios[semana][tema][dia][1] += peso
            if polaridad == 'negativa':
                diarios[semana][tema][dia][0] += peso
            if semana in cerradas:
                cerradas[semana]['conteos'][tema][polaridad] += peso
            afectadas.add(semana)
        for semana in sorted(afectadas):
            comprobar(semana, ahora)
        for semana in caso['cierres'].get(ahora, ()):
            comprobar(semana, ahora)
            cerradas[semana] = {
                'conteos': _clonar_conteos(conteos[semana]),
                'alerto': any(k[0] == semana for k in alertas),
            }
    relevantes = caso['relevantes']
    detectados = sum(1 for k in relevantes if k in alertas and
                     (alertas[k] - inicio_semana(k[0] + 1)).total_seconds() <= 24 * 3600)
    fp = sum(1 for k in alertas if k not in relevantes)
    return {'incidentes': len(relevantes), 'detectados_24h': detectados,
            'fp': fp, 'alertas': len(alertas), 'alertas_detalle': sorted(alertas)}


def calibrar(modelo=None, breve: bool = False) -> tuple[list[dict], dict]:
    modelo = modelo or ClasificadorSentimiento.cargar()
    codigos = ESCENARIOS_CALIBRACION if not breve else ('E01', 'E02')
    semillas = SEMILLAS_CALIBRACION if not breve else (101,)
    parametros = list(itertools.product(DELTA, HS, MIN_NEGATIVAS))
    if breve:
        parametros = parametros[:2]
    casos = [preparar_caso(codigo, semilla, modelo)
             for codigo in codigos for semilla in semillas]
    filas = []
    for delta, h, min_negativas in parametros:
        cuentas = [evaluar_parametros_caso(caso, delta, h, min_negativas) for caso in casos]
        incidentes = sum(c['incidentes'] for c in cuentas)
        alertas = sum(c['alertas'] for c in cuentas)
        detectados = sum(c['detectados_24h'] for c in cuentas)
        fp = sum(c['fp'] for c in cuentas)
        filas.append({'delta': delta, 'h': h, 'min_negativas': min_negativas,
                      'deteccion': detectados / incidentes if incidentes else 0.0,
                      'tasa_fp': fp / alertas if alertas else 0.0,
                      'detectados_24h': detectados, 'incidentes': incidentes,
                      'fp': fp, 'alertas': alertas})
    return filas, elegir_parametros(filas)


def guardar_resultado(filas: list[dict], eleccion: dict) -> dict:
    cfg_ruta = RAIZ / 'config/config.json'
    cfg = json.loads(cfg_ruta.read_text(encoding='utf-8-sig'))
    cfg['cusum_delta'] = float(eleccion['delta'])
    cfg['cusum_h'] = float(eleccion['h'])
    cfg['cusum_min_negativas'] = int(eleccion['min_negativas'])
    ruta_cal = RAIZ / 'experiments/calibracion_fijada.json'
    ruta_grid = RAIZ / 'experiments/resultados/calibracion_rejilla.csv'
    if ruta_cal.exists() or ruta_grid.exists():
        raise FileExistsError('Calibración ya registrada; no se sobrescribió nada.')
    # Escribe archivos solo si se validaron todos los destinos.
    ruta_grid.parent.mkdir(parents=True, exist_ok=True)
    with ruta_grid.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS, lineterminator='\n')
        w.writeheader(); w.writerows(filas)
    documento = {
        'calibracion': 'M2-M4: CUSUM diario',
        'solo_escenarios': list(ESCENARIOS_CALIBRACION),
        'solo_semillas': list(SEMILLAS_CALIBRACION),
        'rejilla': {'delta': DELTA, 'h': HS, 'min_negativas': MIN_NEGATIVAS},
        'criterio': 'maximizar deteccion_24h con tasa_fp estrictamente menor a 0.08',
        'eleccion': eleccion,
        'advertencia': None if eleccion['cumple_fp_calibracion']
                       else 'NINGUNA configuracion cumplio FP<8%; se eligio FP minimo.',
        'fuente': 'predicciones TF-IDF+LR y calendario de ingesta, sin consultar datos de prueba',
    }
    # Se hace el cambio de configuración SOLO después de obtener la selección.
    cfg_ruta.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    ruta_cal.write_text(json.dumps(documento, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return documento


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--breve', action='store_true', help='Ensayo de la rejilla, sin modificar archivos.')
    args = p.parse_args()
    filas, ganadora = calibrar(breve=args.breve)
    if args.breve:
        print('Ensayo (NO es calibración final):', ganadora)
        return
    documento = guardar_resultado(filas, ganadora)
    print('Calibración fijada con semillas 101..105. Configuración:', documento['eleccion'])
    print('ANTES de ejecutar las semillas 11..55, haz commit de config/config.json,')
    print('experiments/calibracion_fijada.json y experiments/resultados/calibracion_rejilla.csv.')
    if not ganadora['cumple_fp_calibracion']:
        print('ADVERTENCIA: ningún parámetro cumplió FP<8%. Reportar incumplimiento.')


if __name__ == '__main__':
    main()
