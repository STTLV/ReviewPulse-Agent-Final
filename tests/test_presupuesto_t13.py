"""Pruebas locales del presupuesto referencial, sin red, sin proveedor."""
import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from experiments.presupuesto_t13 import (
    PRECIOS_PREDETERMINADOS, UMBRAL_PREDETERMINADO, _cargar_tasas,
    rango_estimado, estimar_desde_corridas, entero_tokens, decimal_positivo,
    main,
)


class PruebasPresupuestoReferencia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = _cargar_tasas(PRECIOS_PREDETERMINADOS)
        cls.umbrales = json.loads(UMBRAL_PREDETERMINADO.read_text(encoding='utf-8'))

    def test_plan_david_25_millones_y_juez_extra(self):
        rep = rango_estimado(self.config, self.umbrales)
        self.assertEqual(rep['tokens_previstos'],
                         {'base': 2300000, 'agente': 200000, 'juez': 10000, 'total': 2510000})
        self.assertFalse(rep['autoriza_ejecuciones'])

    def test_costo_escenario_ast_y_sol_condicional(self):
        rep = rango_estimado(self.config, self.umbrales)
        self.assertEqual(Decimal(rep['intervalo_costos_usd_solo_por_composicion_entrada_salida']['minimo_teorico']), Decimal('25.04'))
        self.assertEqual(Decimal(rep['intervalo_costos_usd_solo_por_composicion_entrada_salida']['maximo_teorico']), Decimal('125.2'))
        self.assertEqual(rep['umbral_historico_alcanzable_en_este_escenario'], 'NO')

    def test_20_porciento_salida_marcado_no_medido(self):
        rep = rango_estimado(self.config, self.umbrales, Decimal('20'))
        self.assertEqual(Decimal(rep['supuesto_ilustrativo_no_medido']['total_usd']), Decimal('45.072'))
        self.assertIn('supuesto_ilustrativo_no_medido', rep)

    def test_porcentaje_fuera_rango_bloqueado(self):
        with self.assertRaisesRegex(ValueError, 'entre 0 y 100'):
            rango_estimado(self.config, self.umbrales, Decimal('105'))

    def test_invalida_token_fraccion_o_negativo(self):
        with self.assertRaisesRegex(ValueError, 'entero'):
            entero_tokens('1.5', 'tok')
        with self.assertRaisesRegex(ValueError, 'positivo'):
            entero_tokens('-1', 'tok')

    def test_bloquea_nan_y_tarifas_cero(self):
        with self.assertRaises(ValueError):
            decimal_positivo('NaN', 'tarifa')
        with self.assertRaises(ValueError):
            decimal_positivo('0', 'tarifa')

    def _csv(self, rows):
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name)/'corridas.csv'
        fields = ['sistema','tarea','repeticion','tipo','tokens_entrada','tokens_salida',
                  'tokens_juez_entrada','tokens_juez_salida','tokens_total_entrada',
                  'tokens_total_salida','modelo_principal','modelo_juez']
        with path.open('w', encoding='utf-8',newline='') as f:
            wr = csv.DictWriter(f, fieldnames=fields)
            wr.writeheader()
            wr.writerows(rows)
        return temp, path

    def fila(self, **kw):
        row = dict(sistema='agente',tarea='C01',repeticion='1',tipo='conteo',
                   tokens_entrada='100',tokens_salida='20',
                   tokens_juez_entrada='0',tokens_juez_salida='0',
                   tokens_total_entrada='100',tokens_total_salida='20',
                   modelo_principal='alias-principal',modelo_juez='alias-juez')
        row.update(kw)
        return row

    def test_csv_parcial_reporta_no_completo(self):
        t,p=self._csv([self.fila()])
        try:
            r=estimar_desde_corridas(self.config,self.umbrales,p)
            self.assertFalse(r['contiene_120_filas_sin_validar_catalogo'])
            self.assertEqual(r['tokens_medidos']['principal']['entrada'], 100)
            self.assertEqual(r['costo_principal_referencia_usd'], str(Decimal('0.002')))
        finally: t.cleanup()

    def test_csv_separa_consumo_juez(self):
        t,p=self._csv([self.fila(tipo='reporte', tarea='R01',
                              tokens_juez_entrada='20',tokens_juez_salida='5',
                              tokens_total_entrada='120',tokens_total_salida='25')])
        try:
            r=estimar_desde_corridas(self.config,self.umbrales,p)
            self.assertEqual(r['tokens_medidos']['juez']['entrada'],20)
            self.assertEqual(r['tokens_medidos']['juez']['salida'],5)
            self.assertEqual(Decimal(r['costo_juez_referencia_usd']), Decimal('0.00018'))
        finally: t.cleanup()

    def test_csv_incompatible_no_se_valora(self):
        t,p=self._csv([self.fila(tokens_total_entrada='500')])
        try:
            with self.assertRaisesRegex(ValueError, 'inconsistentes'):
                estimar_desde_corridas(self.config,self.umbrales,p)
        finally: t.cleanup()

    def test_no_mezcla_modelos(self):
        t,p=self._csv([self.fila(), self.fila(sistema='base', modelo_principal='alias-otro')])
        try:
            with self.assertRaisesRegex(ValueError, 'mezclaron'):
                estimar_desde_corridas(self.config,self.umbrales,p)
        finally: t.cleanup()

    def test_rechaza_csv_antiguo(self):
        t = tempfile.TemporaryDirectory()
        try:
            p=Path(t.name)/'viejo.csv'
            p.write_text('sistema,tarea,repeticion\nagente,C01,1\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'columnas'):
                estimar_desde_corridas(self.config,self.umbrales,p)
        finally: t.cleanup()

    def test_error_al_usar_cuota_con_csv(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'corridas.csv'
            p.write_text('', encoding='utf-8')
            with self.assertRaises(SystemExit) as c:
                main(['--corridas',str(p),'--proporcion-salida-ilustrativa','20'])
            self.assertEqual(c.exception.code,2)


if __name__ == '__main__':
    unittest.main()
