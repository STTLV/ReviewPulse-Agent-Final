
"""Prueba de paridad P1 para la reorganizacion de ReviewPulse."""

import tempfile
import unittest
from pathlib import Path

from reviewpulse.ciclo.cierre import ejecutar_simulacion
from reviewpulse.entorno import EntornoHotel
from reviewpulse.escenarios import ESCENARIOS
from reviewpulse.evaluacion import evaluar_corrida

from experiments.linea_base_hito2 import calcular


def correr(escenario: str, semilla: int) -> dict:
    entorno = EntornoHotel(ESCENARIOS[escenario], semilla)
    with tempfile.TemporaryDirectory() as tmp:
        resultado = ejecutar_simulacion(entorno, Path(tmp))
    return evaluar_corrida(entorno, resultado)


class PruebaParidad(unittest.TestCase):

    def test_p2_e02(self):
        m = correr("E02", 11)
        self.assertEqual(
            (m["resenas_clasificadas"], m["resenas_descartadas"], m["reportes_a_tiempo"]),
            (486, 21, 14),
        )

    def test_p3_e11(self):
        m = correr("E11", 11)
        self.assertEqual(
            (m["resenas_clasificadas"], m["resenas_descartadas"],
             m["reportes_a_tiempo"], m["reportes_incompletos"]),
            (487, 20, 14, 2),
        )

    def test_p1_conjunto_de_control(self):
        resumen, detalle = calcular()

        self.assertEqual(resumen["n_control"], 40)
        self.assertEqual(len(detalle), 40)

        metricas = resumen["metricas"]

        self.assertEqual(
            metricas["polaridad"]["linea_base"]["aciertos"], 16
        )
        self.assertEqual(
            metricas["polaridad"]["reviewpulse"]["aciertos"], 32
        )
        self.assertEqual(
            metricas["tema"]["linea_base"]["aciertos"], 10
        )
        self.assertEqual(
            metricas["tema"]["reviewpulse"]["aciertos"], 34
        )


if __name__ == "__main__":
    unittest.main()
