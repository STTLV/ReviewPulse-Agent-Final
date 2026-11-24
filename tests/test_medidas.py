"""Calibración reproducible y métricas sin fugas de prueba."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'experiments'))
sys.path.insert(0, str(RAIZ / 'src'))

from calibrar_cusum import (elegir_parametros, evaluar_parametros_caso,
                           preparar_caso, ESCENARIOS_CALIBRACION,
                           SEMILLAS_CALIBRACION, DELTA, HS, MIN_NEGATIVAS)
from medir_m1_m4 import (COLUMNAS, resumir, cargar_v1, SEMILLAS_PRUEBA)


class PruebasCalibracion(unittest.TestCase):
    def test_elige_mayor_deteccion_con_fp_permitido(self):
        filas = [{'h': 3, 'deteccion': .9, 'tasa_fp': .2},
                 {'h': 4, 'deteccion': .7, 'tasa_fp': .05},
                 {'h': 5, 'deteccion': .6, 'tasa_fp': .01}]
        self.assertEqual(elegir_parametros(filas)['h'], 4)

    def test_fp_ocho_por_ciento_no_es_permitido(self):
        filas = [{'h': 3, 'deteccion': .9, 'tasa_fp': .08},
                 {'h': 4, 'deteccion': .7, 'tasa_fp': .079}]
        self.assertEqual(elegir_parametros(filas)['h'], 4)

    def test_no_hay_apta_fallback_menor_fp(self):
        filas = [{'h': 3, 'deteccion': .8, 'tasa_fp': .2},
                 {'h': 5, 'deteccion': .3, 'tasa_fp': .1}]
        r = elegir_parametros(filas)
        self.assertEqual(r['h'], 5)
        self.assertFalse(r['cumple_fp_calibracion'])

    def test_rechaza_tasas_invalidas(self):
        with self.assertRaises(ValueError):
            elegir_parametros([])
        with self.assertRaises(ValueError):
            elegir_parametros([{'h': 3, 'deteccion': 1.1, 'tasa_fp': 0.0}])

    def test_rejilla_y_semillas_aisladas(self):
        self.assertEqual(len(DELTA) * len(HS) * len(MIN_NEGATIVAS), 60)
        self.assertEqual(set(ESCENARIOS_CALIBRACION), {f'E{i:02d}' for i in range(1,9)})
        self.assertTrue(set(SEMILLAS_CALIBRACION).isdisjoint(SEMILLAS_PRUEBA))

    def test_recalculo_coincide_con_simulacion_real(self):
        from reviewpulse.ciclo.cierre import ejecutar_simulacion
        from reviewpulse.entorno import EntornoHotel
        from reviewpulse.escenarios import ESCENARIOS
        from reviewpulse.evaluacion import evaluar_corrida
        from reviewpulse.modelo import ClasificadorSentimiento
        modelo = ClasificadorSentimiento.cargar()
        for codigo in ('E02', 'E04'):
            with self.subTest(codigo=codigo):
                caso = preparar_caso(codigo, 101, modelo)
                r = evaluar_parametros_caso(caso, .25, 4, 6)
                entorno = EntornoHotel(ESCENARIOS[codigo], 101)
                with tempfile.TemporaryDirectory() as d:
                    med = evaluar_corrida(entorno, ejecutar_simulacion(entorno, Path(d), modelo=modelo))
                for a, b in [('incidentes', 'incidentes_relevantes'),
                             ('detectados_24h', 'detectados_24h'),
                             ('fp', 'alertas_fp'), ('alertas', 'alertas_total')]:
                    self.assertEqual(r[a], med[b], (codigo, a))


class PruebasMedicion(unittest.TestCase):
    def test_resumen_agregado_y_umbral_exclusivo(self):
        filas = [{'incidentes': 2, 'detectados_24h': 2, 'alertas': 10, 'fp': 1, 'reportes_a_tiempo': 14}]
        r = resumir(filas)
        self.assertEqual(r['M2'], 1.0)
        self.assertEqual(r['M3'], 1.0)
        self.assertEqual(r['M4'], 0.1)
        self.assertFalse(r['cumple_M4'])

    def test_sin_alertas_denominador_declarado(self):
        r = resumir([{'incidentes': 0, 'detectados_24h': 0,
                    'alertas': 0, 'fp': 0, 'reportes_a_tiempo': 14}])
        self.assertIsNone(r['M2'])
        self.assertEqual(r['alertas'], 0)
        self.assertEqual(r['M4'], 0.0)

    def test_v1_historica_sin_mutacion(self):
        filas = cargar_v1()
        self.assertEqual(len(filas), 60)
        self.assertEqual({r['regla'] for r in filas}, {'semanal_v1'})
        self.assertEqual(set(COLUMNAS), set(filas[0]))

    def test_calibracion_rechaza_semilla_prueba(self):
        from reviewpulse.modelo import ClasificadorSentimiento
        with self.assertRaises(ValueError):
            preparar_caso('E02', 11, ClasificadorSentimiento.cargar())


if __name__ == '__main__':
    unittest.main()
