"""Pruebas 100% offline del informe previo de la evaluación."""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from experiments.preflight_t13 import (
    cargar_catalogo, construir_plan, inspeccionar_csv, reporte_previo, leer_campos_runner,
)
from experiments.correr import CAMPOS


class PruebasPreflightT13(unittest.TestCase):
    def setUp(self):
        self.tareas = cargar_catalogo(Path("experiments/tareas.yaml"))
        self.plan = construir_plan(self.tareas)
        self.um = {"tareas": 20, "repeticiones": 3, "sistemas": ["agente", "base"],
                   "costo_usd_max_evaluacion": 1.0}

    def test_esquema_runner_estatico_sin_llamadas(self):
        self.assertEqual(leer_campos_runner(Path("experiments/correr.py")), CAMPOS)

    def test_matriz_120_sin_duplicados(self):
        self.assertEqual(len(self.plan), 120)
        self.assertEqual(len({(p['sistema'], p['tarea'], p['repeticion'])
                              for p in self.plan}), 120)

    def test_agente_y_base_60_cada_uno(self):
        self.assertEqual(sum(p['sistema']=='agente' for p in self.plan), 60)
        self.assertEqual(sum(p['sistema']=='base' for p in self.plan), 60)

    def test_seis_dictamenes_previstos(self):
        self.assertEqual(sum(p['necesita_juez'] for p in self.plan), 6)

    def test_nunca_da_autorizacion_de_gasto(self):
        rep = reporte_previo(self.tareas, self.um,
                             inspeccionar_csv(None, self.plan, CAMPOS))
        self.assertFalse(rep['autoriza_ejecucion_real'])
        self.assertTrue(rep['no_realiza_llamadas'])
        self.assertEqual(rep['csv']['pendientes'], 120)

    def test_no_modifica_umbrales(self):
        previo = self.um.copy()
        reporte_previo(self.tareas, self.um, {'filas':0})
        self.assertEqual(previo, self.um)

    def test_umbral_incompatible_falla(self):
        um = dict(self.um, repeticiones=2)
        with self.assertRaisesRegex(ValueError, 'umbrales'):
            reporte_previo(self.tareas, um, {'filas':0})

    def test_csv_antiguo_rechazado(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'corridas.csv'
            p.write_text('sistema,tarea,repeticion\nagente,C01,1\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Esquema'):
                inspeccionar_csv(p, self.plan, CAMPOS)

    def test_csv_parcial_reporta_pendiente(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'corridas.csv'
            with p.open('w', newline='', encoding='utf-8') as f:
                w=csv.DictWriter(f, fieldnames=CAMPOS)
                w.writeheader()
                w.writerow({k: v for k, v in {**self.plan[0], 'estado':'terminado'}.items() if k in CAMPOS})
            r=inspeccionar_csv(p, self.plan, CAMPOS)
            self.assertEqual((r['filas'],r['pendientes']), (1,119))

    def test_csv_duplicado_rechazado(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'corridas.csv'
            with p.open('w',newline='',encoding='utf-8') as f:
                w=csv.DictWriter(f,fieldnames=CAMPOS)
                w.writeheader()
                w.writerow({k: v for k, v in self.plan[0].items() if k in CAMPOS});w.writerow({k: v for k, v in self.plan[0].items() if k in CAMPOS})
            with self.assertRaisesRegex(ValueError,'duplicada'):
                inspeccionar_csv(p,self.plan,CAMPOS)

    def test_csv_clave_ajena_rechazada(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'corridas.csv'
            with p.open('w',newline='',encoding='utf-8') as f:
                w=csv.DictWriter(f,fieldnames=CAMPOS)
                w.writeheader()
                w.writerow({k: v for k, v in {**self.plan[0], 'tarea':'X99'}.items() if k in CAMPOS})
            with self.assertRaisesRegex(ValueError,'ajena'):
                inspeccionar_csv(p,self.plan,CAMPOS)

if __name__=='__main__':
    unittest.main()
