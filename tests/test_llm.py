import unittest
from types import SimpleNamespace

from reviewpulse.config import Ajustes, cargar_ajustes
from reviewpulse.llm import (
    ClienteOpenAI,
    Error401,
    Error500,
    LLMFalso,
    respuesta_herramienta,
)
from reviewpulse.llm import ErrorConTexto


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


class LLMFalsoPrueba(unittest.TestCase):
    def test_entrega_respuesta_de_herramienta(self):
        falso = LLMFalso([respuesta_herramienta("generar_reporte", semana=3)])
        r = falso.chat([], [{"type": "function"}])
        self.assertTrue(r.ok)
        self.assertEqual(r.llamadas[0].nombre, "generar_reporte")
        self.assertEqual(len(falso.llamadas), 1)

    def test_guion_operativo_genera_reporte(self):
        falso = LLMFalso([])
        r = falso.guion_operativo([{"role": "user", "content": "genera el reporte"}])
        self.assertTrue(r.ok)
        self.assertEqual(r.llamadas[0].nombre, "generar_reporte")

    def test_guion_operativo_alarma_compara_y_luego_alerta(self):
        falso = LLMFalso([])
        mensajes = [{"role": "user", "content": "ALARMA semana=4 tema=limpieza observaciones=8"}]
        primero = falso.guion_operativo(mensajes)
        self.assertEqual(primero.llamadas[0].nombre, "comparar_semana")
        segundo = falso.guion_operativo(mensajes)
        self.assertEqual(segundo.llamadas[0].nombre, "emitir_alerta")

    def test_guion_operativo_cierre_genera_reporte(self):
        falso = LLMFalso([])
        r = falso.guion_operativo([
            {"role": "user", "content": "CIERRE semana=7 incompleto=2"}
        ])
        self.assertEqual(r.llamadas[0].nombre, "generar_reporte")
        self.assertIn('"semana": 7', r.llamadas[0].argumentos_crudos)
        self.assertIn('"incompleto": 2', r.llamadas[0].argumentos_crudos)


class ClienteOpenAIPrueba(unittest.TestCase):
    def test_sin_llave_devuelve_no_configurado(self):
        ajuste = Ajustes("u", "", "m", "j", "", 1000)
        r = ClienteOpenAI(ajuste, sdk=SdkFalso([])).chat([])
        self.assertFalse(r.ok)
        self.assertEqual(r.tipo, "no_configurado")

    def test_reintenta_error_500_tres_veces(self):
        ajuste = Ajustes("u", "x", "m", "j", "", 1000)
        sdk = SdkFalso([Error500(), Error500(), Error500()])
        r = ClienteOpenAI(ajuste, sdk=sdk).chat([])
        self.assertFalse(r.ok)
        self.assertEqual(r.tipo, "proveedor")
        self.assertEqual(len(sdk.llamadas), 3)

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
        self.assertNotIn("secreta", r.error)
        self.assertEqual(len(sdk.llamadas), 1)

    def test_error_500(self):
        ajustes = Ajustes("u", "x", "m", "j", "", 1000)
        r = ClienteOpenAI(
            ajustes,
            sdk=SdkFalso([Error500("secreta"), Error500("secreta"), Error500("secreta")]),
        ).chat([])
        self.assertFalse(r.ok)
        self.assertIn("500", r.error)
        self.assertNotIn("secreta", r.error)

    def test_error_con_texto_no_divulga_llave(self):
        ajustes = Ajustes("u", "secreta", "m", "j", "", 1000)
        r = ClienteOpenAI(ajustes, sdk=SdkFalso([ErrorConTexto("secreta fue rechazada")])).chat([])
        self.assertFalse(r.ok)
        self.assertNotIn("secreta", r.error)


if __name__ == "__main__":
    unittest.main()
