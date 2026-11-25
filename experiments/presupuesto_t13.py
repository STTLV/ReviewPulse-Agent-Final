"""Presupuesto referencial T13. SOLO lee archivos locales; sin API, red ni llamadas LLM.

Dos modos:
* Sin --corridas: rangos de costos posibles para la referencia de 2.5 M + 10 k.
* Con --corridas: estima a partir de tokens medidos, conservando la separación de modelos.

Una tarifa pública jamás representa por sí sola el cargo real de la cuenta OmniRoute.
"""
from __future__ import annotations

import argparse
import csv
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
PRECIOS_PREDETERMINADOS = RAIZ / 'experiments' / 'precios_referencia_t13.json'
UMBRAL_PREDETERMINADO = RAIZ / 'experiments' / 'umbrales.json'
CAMPOS_CSV = {
    'sistema', 'tarea', 'repeticion', 'tipo', 'tokens_entrada', 'tokens_salida',
    'tokens_juez_entrada', 'tokens_juez_salida', 'tokens_total_entrada',
    'tokens_total_salida', 'modelo_principal', 'modelo_juez'
}


def decimal_positivo(v: Any, nombre: str, permitir_cero: bool = False) -> Decimal:
    if isinstance(v, bool):
        raise ValueError(f'{nombre} debe ser un numero, no booleano.')
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'{nombre} debe ser un numero valido.') from exc
    if not d.is_finite() or d < 0 or (not permitir_cero and d == 0):
        raise ValueError(f'{nombre} debe ser positivo y finito.')
    return d


def entero_tokens(v: Any, nombre: str) -> int:
    d = decimal_positivo(v, nombre, permitir_cero=True)
    if d != d.to_integral_value():
        raise ValueError(f'{nombre} debe ser entero.')
    return int(d)


def _cargar_tasas(ruta: Path) -> dict:
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    if datos.get('estado') != 'EJEMPLO_CONDICIONAL_NO_AUTORIZA_GASTO':
        raise ValueError('El archivo de referencia debe declarar que no autoriza gastos.')
    for campo in ('principal', 'juez'):
        item = datos.get('tarifas', {}).get(campo, {})
        if not isinstance(item.get('identificador_de_referencia'), str) or not item['identificador_de_referencia'].strip():
            raise ValueError(f'Falta identificador de referencia para {campo}.')
        for tipo in ('entrada', 'salida'):
            decimal_positivo(item.get(f'usd_por_millon_{tipo}'), f'{campo}.{tipo}')
    for campo in ('base', 'agente', 'juez'):
        entero_tokens(datos.get('tokens_previstos', {}).get(campo), campo)
    return datos


def _costo_tokens(entrada: int | Decimal, salida: int | Decimal, tasa: dict) -> Decimal:
    entrada_tasa = decimal_positivo(tasa['usd_por_millon_entrada'], 'tasa_entrada')
    salida_tasa = decimal_positivo(tasa['usd_por_millon_salida'], 'tasa_salida')
    return (Decimal(entrada) * entrada_tasa + Decimal(salida) * salida_tasa) / Decimal(1000000)


def _reporte_base(config: dict, umbrales: dict) -> dict:
    return {
        'estado': 'ESTIMACION_DE_REFERENCIA_NO_FACTURACION',
        'fecha_consulta_referencia': config.get('fecha_consulta_referencia'),
        'fuente_tarifas': config.get('fuente_tarifas'),
        'modelos_referencia': {
            'principal': config['tarifas']['principal']['identificador_de_referencia'],
            'juez': config['tarifas']['juez']['identificador_de_referencia'],
        },
        'umbral_historico_usd_no_modificado': str(umbrales['costo_usd_max_evaluacion']),
        'autoriza_ejecuciones': False,
        'cargo_real_proveedor_usd': None,
        'nota': ('Las tarifas son condicionales al identificador, modalidad, contexto y proveedor. '
                 'Este reporte no consulta OmniRoute ni impone un bloqueo real de gasto.'),
    }


def rango_estimado(config: dict, umbrales: dict, porcentaje_salida: Decimal | None = None) -> dict:
    t = config['tokens_previstos']
    n_base = entero_tokens(t['base'], 'base')
    n_agente = entero_tokens(t['agente'], 'agente')
    n_juez = entero_tokens(t['juez'], 'juez')
    principal = config['tarifas']['principal']
    juez = config['tarifas']['juez']
    tot_principal = n_base + n_agente
    inferior = _costo_tokens(tot_principal, 0, principal) + _costo_tokens(n_juez, 0, juez)
    superior = _costo_tokens(0, tot_principal, principal) + _costo_tokens(0, n_juez, juez)
    inf, sup = sorted([inferior, superior])
    rep = _reporte_base(config, umbrales)
    rep['tipo'] = 'PLAN_SIN_CORRIDAS'
    rep['tokens_previstos'] = {'base': n_base, 'agente': n_agente, 'juez': n_juez,
                               'total': tot_principal + n_juez}
    rep['intervalo_costos_usd_solo_por_composicion_entrada_salida'] = {
        'minimo_teorico': str(inf), 'maximo_teorico': str(sup)
    }
    rep['advertencia_intervalo'] = ('No son limites garantizados de la factura; excluyen '
                                   'reintentos, descuentos, recargos y la variante real.')
    if porcentaje_salida is not None:
        if porcentaje_salida < 0 or porcentaje_salida > 100:
            raise ValueError('La proporcion ilustrativa de salida debe estar entre 0 y 100.')
        cuota = porcentaje_salida / Decimal(100)
        in_principal = Decimal(tot_principal) * (1 - cuota)
        out_principal = Decimal(tot_principal) * cuota
        in_juez = Decimal(n_juez) * (1 - cuota)
        out_juez = Decimal(n_juez) * cuota
        rep['supuesto_ilustrativo_no_medido'] = {
            'porcentaje_salida': str(porcentaje_salida),
            'principal_usd': str(_costo_tokens(in_principal, out_principal, principal)),
            'juez_usd': str(_costo_tokens(in_juez, out_juez, juez)),
            'total_usd': str(_costo_tokens(in_principal, out_principal, principal) +
                             _costo_tokens(in_juez, out_juez, juez)),
        }
    rep['umbral_historico_alcanzable_en_este_escenario'] = (
        'NO' if inf > decimal_positivo(umbrales['costo_usd_max_evaluacion'], 'umbral')
        else 'INDETERMINADO_CON_ESTIMACIONES'
    )
    return rep


def estimar_desde_corridas(config: dict, umbrales: dict, csv_path: Path) -> dict:
    """Calcula importes orientativos sobre consumo reportado, nunca factura real."""
    with csv_path.open('r', encoding='utf-8-sig', newline='') as archivo:
        reader = csv.DictReader(archivo)
        if not reader.fieldnames or not CAMPOS_CSV.issubset(set(reader.fieldnames)):
            raise ValueError('CSV no tiene columnas de consumo nuevas de T13.')
        filas = list(reader)
    if not filas:
        raise ValueError('CSV sin ejecuciones.')
    if len(filas) > 120:
        raise ValueError('Más de 120 ejecuciones: revisar duplicados.')
    resultado = {'principal': {'entrada': 0, 'salida': 0}, 'juez': {'entrada': 0, 'salida': 0}}
    claves = set()
    modelos_principal, modelos_juez = set(), set()
    for fila in filas:
        if fila['sistema'] not in ('agente', 'base'):
            raise ValueError('Sistema no reconocido.')
        if fila['modelo_principal'] == fila['modelo_juez'] or not fila['modelo_principal'] or not fila['modelo_juez']:
            raise ValueError('Modelos no definidos o idénticos.')
        modelos_principal.add(fila['modelo_principal'])
        modelos_juez.add(fila['modelo_juez'])
        clave = (fila['sistema'], fila['tarea'], fila['repeticion'])
        if clave in claves:
            raise ValueError('Ejecuciones duplicadas: ' + repr(clave))
        claves.add(clave)
        for modelo, prefijo in [('principal', 'tokens'), ('juez', 'tokens_juez')]:
            for tipo in ('entrada', 'salida'):
                resultado[modelo][tipo] += entero_tokens(fila[f'{prefijo}_{tipo}'], f'{prefijo}_{tipo}')
        for tipo in ('entrada', 'salida'):
            total = entero_tokens(fila[f'tokens_total_{tipo}'], f'tokens_total_{tipo}')
            partes = (entero_tokens(fila[f'tokens_{tipo}'], f'tokens_{tipo}') +
                      entero_tokens(fila[f'tokens_juez_{tipo}'], f'tokens_juez_{tipo}'))
            if total != partes:
                raise ValueError(f'Tokens totales inconsistentes en {clave}.')
        if fila['tipo'] != 'reporte' and (entero_tokens(fila['tokens_juez_entrada'], 'tokens_juez_entrada') or entero_tokens(fila['tokens_juez_salida'], 'tokens_juez_salida')):
            raise ValueError('Juez consumió tokens fuera de reporte.')
    if len(modelos_principal) != 1 or len(modelos_juez) != 1:
        raise ValueError('Se mezclaron identificadores de modelos en CSV.')
    c_principal = _costo_tokens(resultado['principal']['entrada'], resultado['principal']['salida'],
                                config['tarifas']['principal'])
    c_juez = _costo_tokens(resultado['juez']['entrada'], resultado['juez']['salida'],
                           config['tarifas']['juez'])
    rep = _reporte_base(config, umbrales)
    rep.update({
        'tipo': 'CSV_CON_CONSUMO_REPORTADO',
        'filas_recibidas': len(filas),
        'contiene_120_filas_sin_validar_catalogo': len(filas) == 120 and len(claves) == 120,
        'modelos_csv': {'principal': next(iter(modelos_principal)), 'juez': next(iter(modelos_juez))},
        'ids_coinciden_con_tarifas_referencia': (next(iter(modelos_principal)) == config['tarifas']['principal']['identificador_de_referencia'] and next(iter(modelos_juez)) == config['tarifas']['juez']['identificador_de_referencia']),
        'tokens_medidos': resultado,
        'costo_principal_referencia_usd': str(c_principal),
        'costo_juez_referencia_usd': str(c_juez),
        'costo_total_referencia_usd': str(c_principal + c_juez),
        'advertencia': ('Un CSV con 120 filas no garantiza por si solo la matriz correcta: usar analizar.py. '
                        'Si el modelo de OmniRoute es un alias, verificar el modelo subyacente antes de valorar el importe.'),
    })
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tarifas', type=Path, default=PRECIOS_PREDETERMINADOS)
    ap.add_argument('--umbrales', type=Path, default=UMBRAL_PREDETERMINADO)
    ap.add_argument('--proporcion-salida-ilustrativa', type=str,
                    help='Porcentaje SUPUESTO de tokens de salida, NO medido, p.ej. 20')
    ap.add_argument('--corridas', type=Path, help='CSV REAL con columnas separadas de T13; sin --corridas usa solo plan de David')
    args = ap.parse_args(argv)
    try:
        config = _cargar_tasas(args.tarifas)
        umbrales = json.loads(args.umbrales.read_text(encoding='utf-8'))
        cuota = (decimal_positivo(args.proporcion_salida_ilustrativa, 'porcentaje', permitir_cero=True)
                 if args.proporcion_salida_ilustrativa is not None else None)
        if args.corridas and cuota is not None:
            raise ValueError('No mezclar supuesto de salida con datos de corridas reales.')
        if args.corridas:
            rep = estimar_desde_corridas(config, umbrales, args.corridas)
        else:
            rep = rango_estimado(config, umbrales, cuota)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        ap.error(str(exc))
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
