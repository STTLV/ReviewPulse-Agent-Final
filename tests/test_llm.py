import unittest
from types import SimpleNamespace
from unittest.mock import patch

from reviewpulse.config import Ajustes, cargar_ajustes
from reviewpulse.llm import (
    ClienteOpenAI,
    LLMFalso,
    guion_operativo,
    respuesta_herramienta,
)


class ErrorConEstado(Exception):
    def __init__(self, codigo, mensaje="error simulado"):
        super().__init__(mensaje)
        self.status_code = codigo


class Error401(ErrorConEstado):
    def __init__(self, mensaje="error simulado"):
        super().__init__(401, mensaje)


class Error500(ErrorConEstado):
    def __init__(self, mensaje="error simulado"):
        super().__init__(500, mensaje)


class ErrorConTexto(Exception):
    pass


class SdkFalso:
    """Doble secuencial del SDK usado por las pruebas del ClienteOpenAI."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.chat = type("Chat", (), {})()
        self.chat.completions = self

    def create(self, **parametros):
        self.llamadas.append(parametros)
        if not self.respuestas:
            raise AssertionError("El SDK falso recibió una llamada adicional")
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, BaseException):
            raise respuesta
        return respuesta


class AjustesLLMPrueba(unittest.TestCase):
    def test_la_llave_no_aparece_en_repr(self):
        ajustes = Ajustes("u", "secreta", "", "J", "C", 1000)
        self.assertNotIn("secreta", repr(ajustes))
        self.assertNotIn("C", repr(ajustes))

    def test_cargar_ajustes_desde_diccionario(self):
        ajustes = cargar_ajustes({
            "LLM_BASE_URL": "https://ejemplo.test/v1",
            "LLM_API_KEY": "secreta",
            "LLM_MODEL": "modelo-a",
            "LLM_JUEZ_MODEL": "modelo-b",
            "APP_CODIGO_ACCESO": "codigo",
            "LLM_TOPE_TOKENS_DIA": "250",
        })
        self.assertEqual(ajustes.llm_tope_tokens_dia, 250)
        self.assertEqual(ajustes.llm_model, "modelo-a")

    def test_valores_openai_por_defecto_vacios(self):
        ajustes = cargar_ajustes({})
        self.assertEqual(ajustes.llm_base_url, "")
        self.assertEqual(ajustes.llm_model, "")
        self.assertEqual(ajustes.llm_juez_model, "")


class LLMFalsoPrueba(unittest.TestCase):
    def test_entrega_respuesta_de_herramienta(self):
        falso = LLMFalso([respuesta_herramienta("generar_reporte", semana=3)])
        r = falso.chat([], [{"type": "function"}])
        self.assertTrue(r.ok)
        self.assertEqual(r.llamadas[0].nombre, "generar_reporte")
        self.assertEqual(len(falso.llamadas), 1)

    def test_guion_operativo_genera_reporte(self):
        r = guion_operativo([{"role": "user", "content": "genera el reporte"}])
        self.assertTrue(r.ok)
        self.assertEqual(r.llamadas[0].nombre, "generar_reporte")

    def test_guion_operativo_alarma_sin_hallazgo_termina_sin_alertar(self):
        usuario = {"role": "user", "content": "ALARMA semana=4 tema=limpieza observaciones=8"}
        compara = guion_operativo([usuario])
        self.assertEqual(compara.llamadas[0].nombre, "comparar_semana")
        self.assertIn('"observaciones": 8', compara.llamadas[0].argumentos_crudos)

        mensajes = [
            usuario,
            compara.mensaje_asistente,
            {"role": "tool", "tool_call_id": compara.llamadas[0].id,
             "content": '{"hubo_alarma": false, "error": null}'},
        ]
        final = guion_operativo(mensajes)
        self.assertEqual(final.llamadas, [])
        self.assertIn("No hubo alarma", final.texto)

    def test_guion_operativo_alarma_emite_solo_tras_confirmacion_y_termina(self):
        usuario = {"role": "user", "content": "ALARMA semana=4 tema=limpieza observaciones=8"}
        compara = guion_operativo([usuario])
        mensajes = [
            usuario,
            compara.mensaje_asistente,
            {"role": "tool", "tool_call_id": compara.llamadas[0].id,
             "content": '{"hubo_alarma": true}'},
        ]
        alerta = guion_operativo(mensajes)
        self.assertEqual(alerta.llamadas[0].nombre, "emitir_alerta")
        mensajes.extend([
            alerta.mensaje_asistente,
            {"role": "tool", "tool_call_id": alerta.llamadas[0].id, "content": "ok"},
        ])
        final = guion_operativo(mensajes)
        self.assertEqual(final.llamadas, [])
        self.assertIn("Alerta emitida", final.texto)

    def test_guion_operativo_cierre_genera_reporte(self):
        usuario = {"role": "user", "content": "CIERRE semana=7 incompleto=2"}
        reporte = guion_operativo([usuario])
        self.assertEqual(reporte.llamadas[0].nombre, "generar_reporte")
        self.assertIn('"semana": 7', reporte.llamadas[0].argumentos_crudos)
        self.assertIn('"incompleto": 2', reporte.llamadas[0].argumentos_crudos)

        mensajes = [
            usuario,
            reporte.mensaje_asistente,
            {"role": "tool", "tool_call_id": reporte.llamadas[0].id,
             "content": '{"reporte":"listo"}'},
        ]
        final = guion_operativo(mensajes)
        self.assertEqual(final.llamadas, [])
        self.assertIn("Reporte de la semana 7 generado", final.texto)
        self.assertEqual(guion_operativo(mensajes).llamadas, [])


class ClienteOpenAIPrueba(unittest.TestCase):
    def test_sin_llave_devuelve_no_configurado(self):
        ajuste = Ajustes("u", "", "m", "j", "", 1000)
        r = ClienteOpenAI(ajuste, sdk=SdkFalso([])).chat([])
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "no_configurado")

    def test_reintenta_dos_errores_500_y_luego_ok(self):
        ajuste = Ajustes("u", "x", "m", "j", "", 1000)
        respuesta = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )
        sdk = SdkFalso([Error500(), Error500(), respuesta])
        with patch("reviewpulse.llm.cliente.time.sleep") as dormir:
            r = ClienteOpenAI(ajuste, sdk=sdk).chat([])
        self.assertTrue(r.ok)
        self.assertEqual(r.texto, "ok")
        self.assertEqual(len(sdk.llamadas), 3)
        self.assertEqual([llamada.args[0] for llamada in dormir.call_args_list], [0.5, 1.0])

    def test_parametros_temperature_y_timeout(self):
        ajuste = Ajustes("u", "x", "m", "j", "", 1000)
        respuesta = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )
        sdk = SdkFalso([respuesta])
        r = ClienteOpenAI(ajuste, sdk=sdk).chat([])
        self.assertTrue(r.ok)
        self.assertEqual(sdk.llamadas[0]["temperature"], 0)
        self.assertEqual(sdk.llamadas[0]["timeout"], 60)
    def test_respuesta_texto_y_llamadas_de_herramienta(self):
        ajuste = Ajustes("u", "secreta", "m", "j", "", 1000)
        mensaje = SimpleNamespace(
            content="Resumen",
            tool_calls=[SimpleNamespace(
                id="call-1",
                function=SimpleNamespace(name="generar_reporte", arguments='{"semana": 3}')
            )]
        )
        respuesta = SimpleNamespace(
            choices=[SimpleNamespace(message=mensaje)],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7),
        )
        sdk = SdkFalso([respuesta])

        r = ClienteOpenAI(ajuste, sdk=sdk).chat([{"role": "user", "content": "Genera"}],
                                                 [{"type": "function", "function": {"name": "generar_reporte"}}])

        self.assertTrue(r.ok)
        self.assertEqual(r.texto, "Resumen")
        self.assertEqual(r.llamadas[0].id, "call-1")
        self.assertEqual(r.llamadas[0].nombre, "generar_reporte")
        self.assertEqual(r.uso.entrada, 12)
        self.assertEqual(r.uso.salida, 7)
        self.assertEqual(sdk.llamadas[0]["model"], "m")
        self.assertIn("tools", sdk.llamadas[0])

    def test_error_401_no_incluye_llave(self):
        ajustes = Ajustes("u", "secreta", "m", "j", "", 1000)
        sdk = SdkFalso([Error401("secreta")])
        r = ClienteOpenAI(ajustes, sdk=sdk).chat([])
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "autenticacion")
        self.assertEqual(len(sdk.llamadas), 1)

    def test_error_500(self):
        ajustes = Ajustes("u", "x", "m", "j", "", 1000)
        r = ClienteOpenAI(
            ajustes,
            sdk=SdkFalso([Error500("secreta"), Error500("secreta"), Error500("secreta")]),
        ).chat([])
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "proveedor")

    def test_error_con_texto_no_divulga_llave(self):
        ajustes = Ajustes("u", "secreta", "m", "j", "", 1000)
        r = ClienteOpenAI(
            ajustes,
            sdk=SdkFalso([ErrorConTexto("secreta fue rechazada")] * 3),
        ).chat([])
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "proveedor")

    def test_401_402_403_no_se_reintentan(self):
        ajuste = Ajustes("u", "x", "m", "j", "", 1000)
        for codigo, esperado in ((401, "autenticacion"), (402, "proveedor"), (403, "autenticacion")):
            with self.subTest(codigo=codigo):
                sdk = SdkFalso([ErrorConEstado(codigo)])
                with patch("reviewpulse.llm.cliente.time.sleep") as dormir:
                    r = ClienteOpenAI(ajuste, sdk=sdk).chat([])
                self.assertFalse(r.ok)
                self.assertEqual(r.error, esperado)
                self.assertEqual(len(sdk.llamadas), 1)
                dormir.assert_not_called()


if __name__ == "__main__":
    unittest.main()
