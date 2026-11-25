"""Pruebas totalmente sintéticas: NO representan las 120 ejecuciones reales."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.analizar import analizar, resumir, validar_matriz
from experiments import correr, juez
from reviewpulse.llm.cliente import RespuestaLLM, Uso
from experiments.verdad import cargar_tareas


UMBRALES = {
    'bootstrap_remuestreos': 1000,
    'bootstrap_semilla': 2026,
    'exito_agente_minimo': 0.80,
    'errores_herramienta_max': 0.10,
    'version': 'ruta-e-t9-v1',
    'trazabilidad_agente_minima': 0.95,
}


def datos_sinteticos():
    filas = []
    for t in cargar_tareas():
        for sistema in ('agente', 'base'):
            for rep in (1, 2, 3):
                filas.append({
                    'sistema': sistema, 'tarea': t['id'], 'tipo': t['tipo'],
                    'repeticion': str(rep), 'estado': 'terminado',
                    'exito': '1' if sistema == 'agente' else '0',
                    'tokens_entrada': '120', 'tokens_salida': '30',
                    'segundos': '1.0', 'pasos': '2' if sistema == 'agente' else '0',
                    'herramientas': '2' if sistema == 'agente' else '0',
                    'errores_herramienta': '0', 'cifras_no_respaldadas': '0',
                    'motivo': 'completado',
                    'traza_cifras_evaluadas': '0' if sistema == 'agente' else '',
                    'traza_cifras_respaldadas': '0' if sistema == 'agente' else '',
                    'tokens_juez_entrada': '0', 'tokens_juez_salida': '0',
                    'tokens_total_entrada': '120', 'tokens_total_salida': '30',
                    'modelo_principal': 'gpt-6', 'modelo_juez': 'gpt-5.6',
                })
    return filas


class PruebasAnalisis(unittest.TestCase):
    def test_interfaz_plan_resumir(self):
        filas = [{'sistema': 'agente', 'tarea': 'C01', 'exito': 1},
                 {'sistema': 'agente', 'tarea': 'C01', 'exito': 0},
                 {'sistema': 'base', 'tarea': 'C01', 'exito': 0},
                 {'sistema': 'base', 'tarea': 'C01', 'exito': 0}]
        resumen = resumir(filas)
        self.assertEqual((resumen['agente']['exito'], resumen['base']['exito']), (0.5, 0.0))

    def test_matriz_completa_120(self):
        validar_matriz(datos_sinteticos(), cargar_tareas())

    def test_detecta_duplicados(self):
        filas = datos_sinteticos()
        with self.assertRaisesRegex(ValueError, 'duplicada'):
            validar_matriz(filas + [filas[0]], cargar_tareas())

    def test_no_acepta_119(self):
        with self.assertRaisesRegex(ValueError, 'incompleta'):
            validar_matriz(datos_sinteticos()[:-1], cargar_tareas())

    def test_no_acepta_juez_pendiente(self):
        filas = datos_sinteticos()
        filas[0]['estado'] = 'juez_pendiente'
        filas[0]['exito'] = ''
        with self.assertRaisesRegex(ValueError, 'no terminada'):
            validar_matriz(filas, cargar_tareas())

    def test_bootstrap_pareado_por_20_tareas(self):
        rep, grupos, errores = analizar(datos_sinteticos(), cargar_tareas(), UMBRALES)
        self.assertEqual(rep['sistemas']['agente']['exito'], 1)
        self.assertEqual(rep['sistemas']['base']['exito'], 0)
        self.assertEqual(rep['comparacion']['diferencia_exito_agente_menos_base'], 1)
        self.assertEqual(rep['comparacion']['ic_95_bajo'], 1)
        self.assertEqual(rep['comparacion']['ic_95_alto'], 1)
        self.assertEqual(len(errores), 60)

    def test_no_inventa_subgrupos_ni_tarifas(self):
        rep, grupos, _ = analizar(datos_sinteticos(), cargar_tareas(), UMBRALES)
        self.assertIsNone(rep['indicadores']['costo_usd_meta_1'])
        self.assertIsNone(rep['indicadores']['trazabilidad_global_meta_95'])
        self.assertIsNone(rep['indicadores']['cifras_incorrectas_global_meta_5'])
        self.assertEqual(sum(g['estado']=='no_evaluable_sin_metadata' for g in grupos), 8)

    def test_veredicto_no_binario_no_es_fracaso(self):
        with self.assertRaisesRegex(ValueError, 'pendiente'):
            resumir([{'sistema': 'agente', 'exito': ''}])


    def test_consumo_juez_separado_de_principal(self):
        filas = datos_sinteticos()
        for f in filas:
            if f['tipo'] == 'reporte':
                f['tokens_juez_entrada'] = '20'
                f['tokens_juez_salida'] = '5'
                f['tokens_total_entrada'] = '140'
                f['tokens_total_salida'] = '35'
        rep, _, _ = analizar(filas, cargar_tareas(), UMBRALES)
        # R01, 3 repeticiones, 2 sistemas = seis dictamenes de juez.
        self.assertEqual(rep['consumo']['principal_entrada'], 120 * 120)
        self.assertEqual(rep['consumo']['juez_entrada'], 6 * 20)
        self.assertEqual(rep['consumo']['juez_salida'], 6 * 5)
        self.assertIsNone(rep['consumo']['costo_usd_facturado'])


    def test_impide_mezclar_modelos_en_matriz(self):
        filas = datos_sinteticos()
        filas[0]['modelo_principal'] = 'otro-modelo'
        with self.assertRaisesRegex(ValueError, 'modelos distintos'):
            validar_matriz(filas, cargar_tareas())

    def test_valida_inconsistencia_consumo(self):
        filas = datos_sinteticos()
        filas[0]['tokens_total_entrada'] = '999'
        with self.assertRaisesRegex(ValueError, 'incompatible'):
            validar_matriz(filas, cargar_tareas())

    def test_trazabilidad_ponderada_con_numerador_y_denominador(self):
        filas = datos_sinteticos()
        agente = [f for f in filas if f['sistema'] == 'agente']
        for f in agente:
            f['traza_cifras_evaluadas'] = '1'
            f['traza_cifras_respaldadas'] = '1'
        agente[0]['traza_cifras_evaluadas'] = '41'
        agente[0]['traza_cifras_respaldadas'] = '35'
        rep, _, _ = analizar(filas, cargar_tareas(), UMBRALES)
        self.assertEqual(rep['trazabilidad_agente']['cifras_evaluadas'], 100)
        self.assertEqual(rep['trazabilidad_agente']['cifras_respaldadas'], 94)
        self.assertAlmostEqual(rep['trazabilidad_agente']['tasa'], 0.94)
        self.assertFalse(rep['indicadores']['trazabilidad_global_meta_95'])
        self.assertIsNone(rep['indicadores']['cifras_incorrectas_global_meta_5'])

    def test_trazabilidad_incompleta_es_indeterminada(self):
        filas = datos_sinteticos()
        for f in filas:
            if f['sistema'] == 'agente':
                f['traza_cifras_evaluadas'] = '1'
                f['traza_cifras_respaldadas'] = '1'
        fila = next(f for f in filas if f['sistema'] == 'agente')
        fila['traza_cifras_evaluadas'] = fila['traza_cifras_respaldadas'] = ''
        rep, _, _ = analizar(filas, cargar_tareas(), UMBRALES)
        self.assertEqual(rep['trazabilidad_agente']['filas_sin_evento_final'], 1)
        self.assertIsNone(rep['indicadores']['trazabilidad_global_meta_95'])

    def test_runner_separa_tokens_juez_en_reporte(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'memoria.db'
            base.write_bytes(b'base-irrelevante-para-mocks')
            respuesta = ('Resumen de reporte', 100, 20, 1, 0, 0, 'completado', [])
            dictamen = {'veredicto': True, 'tokens_entrada': 11,
                        'tokens_salida': 7, 'criterios': [True]*4}
            with patch.object(correr, '_base', return_value=respuesta), \
                 patch.object(correr, 'evaluar_reporte', return_value=dictamen):
                fila = correr.ejecutar_una({'id':'R01', 'tipo':'reporte',
                    'semana':11, 'pregunta':'Resumen'}, 'base', 1, base,
                    object(), 'gpt-6', 'gpt-5.6', Path(tmp))
            self.assertEqual((fila['tokens_entrada'], fila['tokens_salida']), (100,20))
            self.assertEqual((fila['tokens_juez_entrada'], fila['tokens_juez_salida']), (11,7))
            self.assertEqual((fila['tokens_total_entrada'], fila['tokens_total_salida']), (111,27))
            self.assertEqual((fila['modelo_principal'], fila['modelo_juez']), ('gpt-6','gpt-5.6'))

    def test_juez_invalido_aun_reporta_uso(self):
        class Falso:
            def chat(self, *a, **k):
                return RespuestaLLM(True, texto='no-es-json', uso=Uso(11,7))
        with patch.object(juez, 'hechos_reporte', return_value={'semana': 11}):
            resultado = juez.evaluar_reporte(Falso(), 'juez', 'reporte', Path('no-usar.db'))
        self.assertIsNone(resultado['veredicto'])
        self.assertEqual((resultado['tokens_entrada'], resultado['tokens_salida']), (11,7))

    def test_runner_bloquea_csv_esquema_antiguo(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / 'corridas.csv'
            ruta.write_text('sistema,tarea,repeticion\nagente,C01,1\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Esquema CSV incompatible'):
                correr._leer_hechas(ruta)

    def test_nunca_cambia_umbrales_originales(self):
        original = dict(UMBRALES)
        analizar(datos_sinteticos(), cargar_tareas(), UMBRALES)
        self.assertEqual(UMBRALES, original)


if __name__ == '__main__':
    unittest.main()
