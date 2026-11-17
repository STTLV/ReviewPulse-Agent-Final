"""Comprobaciones mínimas de la línea base del Hito 2."""
import unittest

from pruebas.linea_base_hito2 import calcular


class PruebaComparacionHito2(unittest.TestCase):
    def test_comparacion_mismo_control(self):
        d, filas = calcular()
        self.assertEqual(d["n_control"], 40)
        self.assertEqual(len(filas), 40)
        for campo in ("polaridad", "tema"):
            r = d["metricas"][campo]
            self.assertEqual(r["linea_base"]["n"], r["reviewpulse"]["n"])
            self.assertEqual(r["reviewpulse"]["n"], 40)
            self.assertGreaterEqual(r["reviewpulse"]["exactitud"],
                                    r["linea_base"]["exactitud"])


if __name__ == "__main__":
    unittest.main()
