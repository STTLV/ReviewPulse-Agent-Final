"""Comprobaciones adicionales del Gold de T7 en las métricas M1 de T8."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'experiments'))

from medir_m1_gold import leer_gold, SEMILLAS_REENTRENAMIENTO


class PruebasM1Gold(unittest.TestCase):
    def test_gold_definitivo_valido(self):
        gold = leer_gold()
        self.assertEqual(len(gold), 120)
        self.assertEqual(len({f['id'] for f in gold}), 120)
        self.assertEqual(gold[0]['id'], 'EVAL-001')
        self.assertEqual(gold[-1]['id'], 'EVAL-120')

    def test_reentrenamientos_no_usan_semillas_de_cusum(self):
        self.assertEqual(SEMILLAS_REENTRENAMIENTO, (71, 72, 73, 74, 75))
        self.assertTrue(set(SEMILLAS_REENTRENAMIENTO).isdisjoint({11, 22, 33, 44, 55}))
        self.assertTrue(set(SEMILLAS_REENTRENAMIENTO).isdisjoint({101, 102, 103, 104, 105}))


if __name__ == '__main__':
    unittest.main()
