"""T13 · Análisis reproducible de las corridas de ReviewPulse (SIN llamadas LLM).

Lee exclusivamente `corridas.csv` de T9. No modifica umbrales ni datos de T8.
Por defecto EXIGE las 120 ejecuciones, un veredicto 0/1 por fila y claves únicas.
Separa el consumo del sistema principal del juez. No confunde trazabilidad
respecto a herramientas con exactitud factual global ni costo real facturado.
Los indicadores no observables en el CSV se dejan explícitamente PENDIENTES.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from experiments.verdad import bootstrap_diferencia, cargar_tareas
except ModuleNotFoundError:  # ejecución directa desde experiments/
    from verdad import bootstrap_diferencia, cargar_tareas

RAIZ = Path(__file__).resolve().parents[1]
SISTEMAS = ('agente', 'base')
REPETICIONES = (1, 2, 3)
TIPOS_SIN_META = ('plataforma', 'longitud', 'tema', 'errores_tipeo')
CAMPOS_ERRORES = ('sistema', 'tarea', 'repeticion', 'tipo_tarea', 'motivo',
                  'ruta_traza_relativa', 'tipo_error', 'evidencia',
                  'hipotesis_causa', 'revision_humana')


def _binario(valor: object) -> int:
    if valor is True or valor == 1 or valor == '1':
        return 1
    if valor is False or valor == 0 or valor == '0':
        return 0
    raise ValueError('Éxito pendiente/no binario: ' + repr(valor))


def _no_negativo(valor: object, campo: str) -> float:
    try:
        n = float(valor)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'Campo numérico inválido: {campo}={valor!r}') from exc
    if not math.isfinite(n) or n < 0:
        raise ValueError(f'Campo numérico inválido: {campo}={valor!r}')
    return n


def resumir(filas: list[dict]) -> dict:
    """Interfaz del plan: éxito y n por sistema; nunca inventa veredictos faltantes."""
    datos = {s: [] for s in SISTEMAS}
    for fila in filas:
        sistema = fila.get('sistema')
        if sistema not in datos:
            raise ValueError('Sistema inesperado: ' + str(sistema))
        datos[sistema].append(_binario(fila.get('exito')))
    return {s: {'n': len(v), 'exito': sum(v) / len(v) if v else None}
            for s, v in datos.items()}


def validar_matriz(filas: list[dict], tareas: list[dict]) -> None:
    """Impide publicar como final un CSV incompleto, duplicado o inconcluso."""
    por_id = {t['id']: t['tipo'] for t in tareas}
    ids = set(por_id)
    if len(ids) != 20:
        raise ValueError('El catálogo no contiene exactamente 20 tareas.')
    esperadas = {(s, t, r) for s in SISTEMAS for t in ids for r in REPETICIONES}
    encontradas = set()
    modelos = set()
    for f in filas:
        try:
            clave = (f['sistema'], f['tarea'], int(f['repeticion']))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('Faltan campos clave del CSV.') from exc
        modelo_principal = f.get('modelo_principal', '').strip()
        modelo_juez = f.get('modelo_juez', '').strip()
        if not modelo_principal or not modelo_juez or modelo_principal == modelo_juez:
            raise ValueError(f'Identificadores de modelos invalidos: {clave}')
        modelos.add((modelo_principal, modelo_juez))
        if clave[1] in por_id and f.get('tipo') != por_id[clave[1]]:
            raise ValueError(f'Tipo de tarea incompatible con el catálogo: {clave}')
        if clave in encontradas:
            raise ValueError(f'Ejecución duplicada: {clave}')
        encontradas.add(clave)
        if f.get('estado') != 'terminado':
            raise ValueError(f'Ejecución no terminada: {clave}; estado={f.get("estado")!r}')
        _binario(f.get('exito'))
        for campo in ('tokens_entrada', 'tokens_salida', 'segundos', 'pasos',
                      'herramientas', 'errores_herramienta', 'cifras_no_respaldadas',
                      'tokens_juez_entrada', 'tokens_juez_salida',
                      'tokens_total_entrada', 'tokens_total_salida'):
            _no_negativo(f.get(campo), campo)
        for tipo in ('entrada', 'salida'):
            principal = _no_negativo(f[f'tokens_{tipo}'], f'tokens_{tipo}')
            juez = _no_negativo(f[f'tokens_juez_{tipo}'], f'tokens_juez_{tipo}')
            total = _no_negativo(f[f'tokens_total_{tipo}'], f'tokens_total_{tipo}')
            if abs(principal + juez - total) > 0.000001:
                raise ValueError(f'Consumo total incompatible: {clave} ({tipo})')
        if f['tipo'] != 'reporte' and any(float(f[c]) for c in
                ('tokens_juez_entrada', 'tokens_juez_salida')):
            raise ValueError(f'Juez usado fuera de reportes: {clave}')
        if f['sistema'] == 'agente':
            n, r = f.get('traza_cifras_evaluadas', ''), f.get('traza_cifras_respaldadas', '')
            if (n == '') != (r == ''):
                raise ValueError(f'Traza numerica incompleta: {clave}')
            if n != '':
                for valor in (n, r):
                    if isinstance(valor, bool) or not str(valor).isdigit():
                        raise ValueError(f'Conteos numericos invalidos: {clave}')
                if int(r) > int(n):
                    raise ValueError(f'Cifras respaldadas exceden evaluadas: {clave}')
        if int(float(f['errores_herramienta'])) > int(float(f['herramientas'])):
            raise ValueError(f'Errores de herramienta superan llamadas: {clave}')
    if encontradas != esperadas:
        ausentes = sorted(esperadas - encontradas)
        extras = sorted(encontradas - esperadas)
        raise ValueError(f'Matriz incompleta o con claves inesperadas: '
                         f'{len(encontradas)}/120, faltantes={len(ausentes)}, extras={len(extras)}. '
                         f'Primeras faltantes={ausentes[:4]}')
    if len(filas) != 120:
        raise ValueError(f'Deben existir 120 filas, se recibieron {len(filas)}.')
    if len(modelos) != 1:
        raise ValueError('Se mezclaron identificadores de modelos distintos en las corridas.')


def _promedio_sd(valores: list[float]) -> dict:
    return {'media': statistics.mean(valores) if valores else None,
            'desviacion_estandar': statistics.stdev(valores) if len(valores) > 1 else
            (0.0 if valores else None)}


def analizar(filas: list[dict], tareas: list[dict], umbrales: dict) -> tuple[dict, list[dict], list[dict]]:
    validar_matriz(filas, tareas)
    exito = resumir(filas)
    par = {(f['sistema'], f['tarea'], int(f['repeticion'])): _binario(f['exito']) for f in filas}
    # Bootstrap por CLUSTER de tarea (20 tareas); cada tarea promedia sus 3 repeticiones.
    ids = [t['id'] for t in tareas]
    agente_t = [sum(par['agente', t, r] for r in REPETICIONES) / 3 for t in ids]
    base_t = [sum(par['base', t, r] for r in REPETICIONES) / 3 for t in ids]
    diferencia, bajo, alto = bootstrap_diferencia(
        agente_t, base_t, n=int(umbrales['bootstrap_remuestreos']),
        semilla=int(umbrales['bootstrap_semilla']))

    por_tipo = defaultdict(list)
    for f in filas:
        por_tipo[(f['tipo'], f['sistema'])].append(_binario(f['exito']))
    subgrupos = [dict(dimension='tipo_tarea', valor=tipo, sistema=s,
                      n=len(valores), exitos=sum(valores), tasa_exito=sum(valores) / len(valores),
                      estado='calculado')
                 for (tipo, s), valores in sorted(por_tipo.items())]
    # El CSV T9 no incluye metadatos por reseña de plataforma/longitud/tema/typos.
    for dimension in TIPOS_SIN_META:
        for s in SISTEMAS:
            subgrupos.append(dict(dimension=dimension, valor='', sistema=s,
                                  n='', exitos='', tasa_exito='', estado='no_evaluable_sin_metadata'))

    # La trazabilidad solo se puede afirmar sobre el agente. Cada fila debe
    # tener un evento final numerico; una sola ausente invalida la tasa global.
    filas_agente = [f for f in filas if f['sistema'] == 'agente']
    filas_traza_sin_final = [f for f in filas_agente if
                             f.get('traza_cifras_evaluadas', '') == '' or
                             f.get('traza_cifras_respaldadas', '') == '']
    numerador = sum(int(f['traza_cifras_respaldadas']) for f in filas_agente
                    if f.get('traza_cifras_respaldadas', '') != '')
    denominador = sum(int(f['traza_cifras_evaluadas']) for f in filas_agente
                      if f.get('traza_cifras_evaluadas', '') != '')
    trazabilidad = (numerador / denominador if not filas_traza_sin_final and
                     denominador > 0 else None)

    modelo_principal, modelo_juez = (filas[0]['modelo_principal'], filas[0]['modelo_juez'])
    por_sistema = {}
    for s in SISTEMAS:
        partes = [f for f in filas if f['sistema'] == s]
        tokens_in = [_no_negativo(f['tokens_entrada'], 'tokens_entrada') for f in partes]
        tokens_out = [_no_negativo(f['tokens_salida'], 'tokens_salida') for f in partes]
        juez_in = [_no_negativo(f['tokens_juez_entrada'], 'tokens_juez_entrada') for f in partes]
        juez_out = [_no_negativo(f['tokens_juez_salida'], 'tokens_juez_salida') for f in partes]
        herramientas = sum(_no_negativo(f['herramientas'], 'herramientas') for f in partes)
        errores_herr = sum(_no_negativo(f['errores_herramienta'], 'errores_herramienta') for f in partes)
        conteos = [f for f in partes if f['tipo'] == 'conteo']
        por_sistema[s] = {
            **exito[s],
            'exitos': sum(_binario(f['exito']) for f in partes),
            'tokens_entrada_total': int(sum(tokens_in)),
            'tokens_salida_total': int(sum(tokens_out)),
            'tokens_juez_entrada_total': int(sum(juez_in)),
            'tokens_juez_salida_total': int(sum(juez_out)),
            'tokens_todos_modelos_entrada_total': int(sum(tokens_in) + sum(juez_in)),
            'tokens_todos_modelos_salida_total': int(sum(tokens_out) + sum(juez_out)),
            'tiempo_segundos': _promedio_sd([_no_negativo(f['segundos'], 'segundos') for f in partes]),
            'pasos': _promedio_sd([_no_negativo(f['pasos'], 'pasos') for f in partes]),
            'herramientas_total': int(herramientas),
            'errores_herramienta_total': int(errores_herr),
            'tasa_errores_herramienta': errores_herr / herramientas if herramientas else None,
            'conteos_con_cifra_no_respaldada': sum(_no_negativo(f['cifras_no_respaldadas'], 'cifras_no_respaldadas') > 0 for f in conteos),
            'conteos_evaluados': len(conteos),
            'tasa_conteos_con_cifra_no_respaldada': (
                sum(_no_negativo(f['cifras_no_respaldadas'], 'cifras_no_respaldadas') > 0
                    for f in conteos) / len(conteos) if conteos else None),
        }

    errores = []
    for f in filas:
        if _binario(f['exito']) != 0:
            continue
        ruta = f"trazas/{f['sistema']}_{f['tarea']}_r{f['repeticion']}.jsonl"
        errores.append({'sistema': f['sistema'], 'tarea': f['tarea'],
                        'repeticion': f['repeticion'], 'tipo_tarea': f['tipo'],
                        'motivo': f.get('motivo', ''), 'ruta_traza_relativa': ruta,
                        'tipo_error': '', 'evidencia': '', 'hipotesis_causa': '',
                        'revision_humana': 'pendiente'})

    reporte = {
        'version': 't13-analisis-instrumentado-v2',
        'estado': 'analisis_de_corridas_reales',
        'matriz': {'tareas': 20, 'repeticiones': 3, 'sistemas': 2, 'ejecuciones': 120,
                   'tareas_tipo': {tipo: sum(t['tipo'] == tipo for t in tareas) for tipo in sorted({t['tipo'] for t in tareas})}},
        'metodo': {'bootstrap': 'pareado por tarea (20 clusters), media de 3 repeticiones por sistema',
                   'remuestreos': int(umbrales['bootstrap_remuestreos']),
                   'semilla': int(umbrales['bootstrap_semilla']),
                   'umbrales_version': umbrales.get('version'),
                   'observacion': 'Sin ajuste de umbrales posterior a las corridas.'},
        'sistemas': por_sistema,
        'trazabilidad_agente': {
            'cifras_evaluadas': denominador,
            'cifras_respaldadas': numerador,
            'filas_sin_evento_final': len(filas_traza_sin_final),
            'tasa': trazabilidad,
            'interpretacion': ('Trazabilidad respecto a observaciones de herramientas; '
                               'no equivale a tasa global de cifras factualmente incorrectas.'),
        },
        'consumo': {
            'modelo_principal': modelo_principal,
            'modelo_juez': modelo_juez,
            'principal_entrada': sum(v['tokens_entrada_total'] for v in por_sistema.values()),
            'principal_salida': sum(v['tokens_salida_total'] for v in por_sistema.values()),
            'juez_entrada': sum(v['tokens_juez_entrada_total'] for v in por_sistema.values()),
            'juez_salida': sum(v['tokens_juez_salida_total'] for v in por_sistema.values()),
            'costo_usd_facturado': None,
            'nota': ('Tokens medidos por uso reportado: principal separado del juez. '
                     'Costos reales y tarifas dependen de OmniRoute; no estimados sin precios.'),
        },
        'comparacion': {'diferencia_exito_agente_menos_base': diferencia,
                        'ic_95_bajo': bajo, 'ic_95_alto': alto,
                        'ic_excluye_cero': bool(bajo > 0 or alto < 0),
                        'superioridad_agente_significativa': bool(bajo > 0)},
        'indicadores': {
            'exito_agente_meta_80': por_sistema['agente']['exito'] >= float(umbrales['exito_agente_minimo']),
            'errores_herramienta_agente_meta_10': (None if por_sistema['agente']['tasa_errores_herramienta'] is None
                                                  else por_sistema['agente']['tasa_errores_herramienta'] <= float(umbrales['errores_herramienta_max'])),
            'cifras_incorrectas_global_meta_5': None,
            'trazabilidad_global_meta_95': (None if trazabilidad is None else
                                              trazabilidad >= float(umbrales['trazabilidad_agente_minima'])),
            'costo_usd_meta_1': None,
        },
        'pendientes': [
            'Cifras incorrectas globales: la columna cifras_no_respaldadas solo revisa la ultima linea de tareas de conteo; no es denominador para todas las cifras de todos los tipos.',
            *(['Trazabilidad: faltan eventos finales para ' + str(len(filas_traza_sin_final)) +
               ' corridas del agente o no hay cifras evaluables; resultado indeterminado.']
              if trazabilidad is None else []),
            'Costo USD facturado: se requiere importe real de OmniRoute, modelo exacto y/o tarifas verificadas. El techo diario no es limite estricto en el runner.',
            'Plataforma, longitud, tema y errores de tipeo no están asociados a cada ejecución: subgrupos no evaluables sin instrumentación adicional.',
            'La revisión humana de 2 dictámenes del juez requiere conservar acceso seguro a la respuesta original; T9 solo exporta trazas redactadas.'
        ],
        'errores_para_clasificar': len(errores),
        'meta_clasificacion_manual_10': len(errores) >= 10,
        'revision_juez_manual_preseleccionada': [
            {'sistema': 'agente', 'tarea': 'R01', 'repeticion': 1},
            {'sistema': 'base', 'tarea': 'R01', 'repeticion': 2},
        ],
        'referencia_m1_m4': 'experiments/resultados/m1_m4.csv (T8; no recalcular ni mezclar)',
    }
    return reporte, subgrupos, errores


def _escribir_csv(ruta: Path, filas: list[dict], columnas: tuple[str, ...] | list[str]) -> None:
    with ruta.open('w', newline='', encoding='utf-8') as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        escritor.writeheader()
        escritor.writerows(filas)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entrada', type=Path, default=RAIZ / 'experiments/resultados/corridas.csv')
    parser.add_argument('--salida', type=Path, default=RAIZ / 'experiments/resultados')
    parser.add_argument('--umbrales', type=Path, default=RAIZ / 'experiments/umbrales.json')
    parser.add_argument('--sobrescribir', action='store_true',
                        help='Reescribir solo archivos derivados si se auditaron previamente')
    args = parser.parse_args()
    if not args.entrada.is_file():
        print('PENDIENTE: aún no existe corridas.csv. No se generó ningún resultado ficticio.')
        return 2
    with args.entrada.open(encoding='utf-8-sig', newline='') as archivo:
        filas = list(csv.DictReader(archivo))
    umbrales = json.loads(args.umbrales.read_text(encoding='utf-8'))
    reporte, grupos, errores = analizar(filas, cargar_tareas(), umbrales)
    rutas = {nombre: args.salida / nombre for nombre in ('resumen.json', 'subgrupos.csv', 'errores.csv')}
    existentes = [str(p) for p in rutas.values() if p.exists()]
    if existentes and not args.sobrescribir:
        raise SystemExit('No se sobrescriben archivos existentes sin --sobrescribir: ' + ', '.join(existentes))
    args.salida.mkdir(parents=True, exist_ok=True)
    rutas['resumen.json'].write_text(json.dumps(reporte, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    _escribir_csv(rutas['subgrupos.csv'], grupos,
                  ('dimension', 'valor', 'sistema', 'n', 'exitos', 'tasa_exito', 'estado'))
    _escribir_csv(rutas['errores.csv'], errores, CAMPOS_ERRORES)
    print('ANÁLISIS REAL GENERADO:', str(rutas['resumen.json']))
    print('Errores para clasificar manualmente:', len(errores))
    print('Indicadores no medibles: consultar resumen.json/pendientes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
