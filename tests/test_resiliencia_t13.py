"""Pruebas de resiliencia T13: todos los dobles son locales; jamás usan red."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from experiments import correr
from reviewpulse.llm.cliente import ClienteOpenAI


def _fila(tarea: dict, sistema: str, repeticion: int) -> dict:
    fila = {campo: "" for campo in correr.CAMPOS}
    fila.update({
        "sistema": sistema, "tarea": tarea["id"],
        "tipo": tarea["tipo"], "repeticion": repeticion,
        "estado": "terminado", "exito": 1,
        "tokens_entrada": 7, "tokens_salida": 2,
        "tokens_juez_entrada": 0, "tokens_juez_salida": 0,
        "tokens_total_entrada": 7, "tokens_total_salida": 2,
        "modelo_principal": "modelo-prueba", "modelo_juez": "juez-prueba",
        "traza_cifras_evaluadas": "", "traza_cifras_respaldadas": "",
    })
    return fila


class PruebasResilienciaT13(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="reviewpulse_t13_resiliencia_")
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.salida = self.raiz / "corridas.csv"
        self.tareas = [
            {"id": "PRUEBA_A", "tipo": "conteo"},
            {"id": "PRUEBA_B", "tipo": "conteo"},
        ]
        self.fake = lambda tarea, sistema, repeticion, *_args, **_kwargs: _fila(tarea, sistema, repeticion)

    def _ejecutar_lote(self, limite=None):
        return correr.ejecutar_lote(
            "base", 1, [], limite, self.raiz / "base-falsa.db", self.salida,
            object(), "modelo-prueba", "juez-prueba"
        )

    def _leer_filas(self):
        with self.salida.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def test_dos_lotes_reanudan_sin_repetir_claves_guardadas(self):
        with patch.object(correr, "cargar_tareas", return_value=self.tareas), \
             patch.object(correr, "ejecutar_una", side_effect=self.fake) as doble:
            uno = self._ejecutar_lote(limite=1)
            self.assertEqual(uno["ejecuciones_nuevas"], 1)
            self.assertTrue(uno["limite_alcanzado"])
            dos = self._ejecutar_lote(limite=1)
            self.assertEqual(dos["ejecuciones_nuevas"], 1)
            self.assertEqual(doble.call_count, 2)
        filas = self._leer_filas()
        self.assertEqual({f["tarea"] for f in filas}, {"PRUEBA_A", "PRUEBA_B"})
        self.assertEqual(len(filas), 2)
        self.assertFalse(self.salida.with_name(self.salida.name + ".pendiente.json").exists())

    def test_si_se_interrumpe_antes_del_csv_marcador_bloquea_repeticion(self):
        with patch.object(correr, "cargar_tareas", return_value=self.tareas), \
             patch.object(correr, "ejecutar_una", side_effect=RuntimeError("fallo simulado")) as doble:
            with self.assertRaisesRegex(RuntimeError, "fallo simulado"):
                self._ejecutar_lote(limite=1)
            marcador = self.salida.with_name(self.salida.name + ".pendiente.json")
            self.assertTrue(marcador.is_file())
            registro = json.loads(marcador.read_text(encoding="utf-8"))
            self.assertEqual((registro["tarea"], registro["repeticion"]), ("PRUEBA_A", 1))
            self.assertEqual(self._leer_filas(), [])
            with self.assertRaisesRegex(RuntimeError, "pendiente de conciliación"):
                self._ejecutar_lote(limite=1)
            self.assertEqual(doble.call_count, 1)

    def test_con_marcador_pendiente_no_se_abre_csv_nuevo(self):
        marcador = self.salida.with_name(self.salida.name + ".pendiente.json")
        marcador.write_text('{"estado":"EN_CURSO_NO_REEJECUTAR_AUTOMATICAMENTE"}', encoding="utf-8")
        with patch.object(correr, "cargar_tareas", return_value=self.tareas), \
             patch.object(correr, "ejecutar_una") as doble:
            with self.assertRaisesRegex(RuntimeError, "pendiente de conciliación"):
                self._ejecutar_lote()
            self.assertFalse(self.salida.exists())
            doble.assert_not_called()

    def test_csv_duplicado_impide_reanudar(self):
        with self.salida.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=correr.CAMPOS)
            w.writeheader()
            w.writerow(_fila(self.tareas[0], "base", 1))
            w.writerow(_fila(self.tareas[0], "base", 1))
        with self.assertRaisesRegex(ValueError, "duplicada"):
            correr._leer_hechas(self.salida)

    def test_identificador_fuera_del_protocolo_impide_reanudar(self):
        with self.salida.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=correr.CAMPOS)
            w.writeheader()
            w.writerow(_fila(self.tareas[0], "base", 99))
        with self.assertRaisesRegex(ValueError, "fuera del protocolo"):
            correr._leer_hechas(self.salida)

    def test_un_intento_local_no_hace_reintentos(self):
        class SDKFalso:
            def __init__(self):
                self.llamadas = 0
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

            def create(self, **_kwargs):
                self.llamadas += 1
                raise RuntimeError("red simulada sin proveedor")

        ajuste = SimpleNamespace(llm_base_url="https://invalid.example", llm_api_key="falso",
                                 llm_model="modelo-falso", llm_tope_tokens_dia=1)
        sdk = SDKFalso()
        cliente = ClienteOpenAI(ajuste, sdk=sdk, max_intentos=1)
        with patch("reviewpulse.llm.cliente.time.sleep", side_effect=AssertionError("no dormir")):
            respuesta = cliente.chat([{"role": "user", "content": "prueba local"}])
        self.assertFalse(respuesta.ok)
        self.assertEqual(sdk.llamadas, 1)
        self.assertEqual(cliente.solicitudes, 1)

    def test_runner_usa_cliente_con_un_intento_explicitamente(self):
        import inspect
        codigo = inspect.getsource(correr.main)
        self.assertIn("ClienteOpenAI(ajustes, max_intentos=1)", codigo)

    def test_desactivado_no_hace_ninguna_llamada(self):
        class SDKFalso:
            def __init__(self):
                self.llamadas = 0
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
            def create(self, **_kwargs):
                self.llamadas += 1
                raise AssertionError("No debe invocarse")
        ajuste = SimpleNamespace(llm_base_url="https://invalid.example", llm_api_key="falso",
                                 llm_model="modelo-falso", llm_tope_tokens_dia=0)
        sdk = SDKFalso()
        respuesta = ClienteOpenAI(ajuste, sdk=sdk, max_intentos=1).chat(
            [{"role": "user", "content": "prueba local"}])
        self.assertEqual(respuesta.error, "no_configurado")
        self.assertEqual(sdk.llamadas, 0)


if __name__ == "__main__":
    unittest.main()
