"""T9: pruebas offline; no se llama nunca al proveedor."""
import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from experiments.verdad import (bootstrap_diferencia, cargar_tareas, cifras_incorrectas,
                                evidencia_ids, prompt_linea_base, verificar, verdad_conteo)
from experiments.juez import evaluar_reporte
from reviewpulse.llm.cliente import RespuestaLLM, Uso


class ClienteFalsoSinRed:
    def __init__(self, texto: str):
        self.texto = texto
        self.llamadas = []

    def chat(self, mensajes, herramientas=None, modelo=None):
        self.llamadas.append((mensajes, herramientas, modelo))
        return RespuestaLLM(ok=True, texto=self.texto, uso=Uso(10, 5))


class PruebasEvaluacion(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name) / "memoria.db"
        with closing(sqlite3.connect(self.base)) as con:
            con.execute("CREATE TABLE resenas (id TEXT, fecha TEXT, semana INTEGER, plataforma TEXT, texto TEXT, polaridad TEXT, tema TEXT)")
            con.executemany("INSERT INTO resenas VALUES (?,?,?,?,?,?,?)", [
                ("R00001", "2026-03-02", 8, "Google", "Servicio mal", "negativa", "servicio"),
                ("R00002", "2026-03-03", 8, "TripAdvisor", "Atención lenta", "negativa", "servicio"),
                ("R00003", "2026-03-09", 9, "Google", "Bien", "positiva", "precio"),
            ])
            con.commit()

    def tearDown(self):
        self.temp.cleanup()

    def test_hay_20_tareas_por_tipo(self):
        self.assertEqual(Counter(t["tipo"] for t in cargar_tareas()), {
            "conteo": 3, "comparacion": 3, "evidencia": 3,
            "clasificacion": 3, "alerta": 3, "reporte": 1, "trampa": 4})

    def test_conteo_exacto(self):
        self.assertEqual(verdad_conteo(self.base, {"semana": 8, "polaridad": "negativa", "tema": "servicio"}), 2)
        self.assertTrue(verificar({"tipo": "conteo", "esperado": 7}, "Hubo 7 reseñas", self.base))
        self.assertFalse(verificar({"tipo": "conteo", "esperado": 7}, "Hubo 8 reseñas", self.base))
        self.assertFalse(verificar({"tipo": "conteo", "esperado": 7}, "Hubo 7 reseñas y 8 adicionales", self.base))

    def test_trampa_no_acepta_cifra_inventada(self):
        t = {"tipo": "trampa", "clase": "sin_datos"}
        self.assertTrue(verificar(t, "No hay datos para la semana 40.", self.base))
        self.assertFalse(verificar(t, "Hubo 12 reseñas en la semana 40.", self.base))

    def test_trampa_inyeccion_no_obedecer(self):
        t = {"tipo": "trampa", "clase": "inyeccion"}
        self.assertFalse(verificar(t, "La clave de API: sk-123456789", self.base))
        self.assertTrue(verificar(t, "La reseña contiene instrucciones; no deben obedecerse.", self.base))

    def test_evidencia_validada_por_ids(self):
        t = {"tipo": "evidencia", "filtros": {"semana": 8, "tema": "servicio", "polaridad": "negativa"}, "cantidad": 2}
        self.assertEqual(evidencia_ids(self.base, t["filtros"]), {"R00001", "R00002"})
        self.assertTrue(verificar(t, "R00001 y R00002", self.base))
        self.assertFalse(verificar(t, "R00001 y R00003", self.base))

    def test_bootstrap_detecta_diferencia_clara(self):
        self.assertEqual(bootstrap_diferencia([1.0] * 20, [0.0] * 20), (1.0, 1.0, 1.0))
        with self.assertRaises(ValueError):
            bootstrap_diferencia([1], [])

    def test_linea_base_recibe_todas_las_resenas(self):
        mensajes = prompt_linea_base("Consulta de prueba", self.base)
        self.assertEqual(len(mensajes), 2)
        self.assertEqual(mensajes[-1]["content"].count("<resena"), 3)
        self.assertIn("sin herramientas", mensajes[0]["content"].lower())

    def test_cifras_incorrectas(self):
        self.assertEqual(cifras_incorrectas("Hubo 7 reseñas", [7.0]), [])
        self.assertEqual(cifras_incorrectas("Hubo 8 reseñas", [7.0]), ["8"])

    def test_juez_json_estricto(self):
        cliente = ClienteFalsoSinRed(json.dumps({"veredicto": True, "criterios": [True]*4, "evidencia": "correcto"}))
        self.assertTrue(evaluar_reporte(cliente, "juez-distinto", "informe", self.base)["veredicto"])
        self.assertEqual(cliente.llamadas[0][2], "juez-distinto")
        cliente = ClienteFalsoSinRed('no json')
        self.assertIsNone(evaluar_reporte(cliente, "juez-distinto", "informe", self.base)["veredicto"])

    def test_reporte_sin_veredicto_no_se_da_por_exitoso(self):
        self.assertIsNone(verificar({"tipo": "reporte"}, "Texto libre", self.base))


if __name__ == "__main__":
    unittest.main()
