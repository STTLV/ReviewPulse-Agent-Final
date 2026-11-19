
"""Prueba de paridad P1 para la reorganizacion de ReviewPulse."""

import unittest

from experiments.linea_base_hito2 import calcular


class PruebaParidad(unittest.TestCase):

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
