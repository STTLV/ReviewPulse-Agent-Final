"""Contrato HTTP de la API FastAPI: pruebas sintéticas, aisladas y sin red."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from reviewpulse.config import Ajustes
from reviewpulse.api.rutas import SolicitudChat, crear_router
from reviewpulse.entorno import EntornoHotel
from reviewpulse.llm.cliente import Uso
from reviewpulse.llm.falso import LLMFalso, respuesta_herramienta, respuesta_texto
from reviewpulse.memoria import RepositorioHistorico, conteo_vacio
from reviewpulse.modelo import ClasificadorSentimiento
from reviewpulse.api import crear_app


_API_KEY_PRUEBA = "llm-key-sintetica-no-real"
_CODIGO_PRUEBA = "codigo-acceso-sintetico-no-real"


class _CapturadorLogs(logging.Handler):
    def __init__(self):
        super().__init__()
        self.registros: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.registros.append(self.format(record))


class PruebasAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.carpeta = Path(self.tmp.name)
        self.db_path = self.carpeta / "demo.sqlite3"
        self._env = patch.dict(os.environ, {
            "REVIEWPULSE_DB_PATH": str(self.db_path),
        })
        self._env.start()
        self.addCleanup(self._env.stop)
        self.headers = {"X-Codigo-Acceso": _CODIGO_PRUEBA}

    def ajustes(self, tope: int = 10000) -> Ajustes:
        return Ajustes(
            llm_base_url="https://router.invalid/v1",
            llm_api_key=_API_KEY_PRUEBA,
            llm_model="modelo-sintetico",
            llm_juez_model="juez-sintetico",
            app_codigo_acceso=_CODIGO_PRUEBA,
            llm_tope_tokens_dia=tope,
        )

    def crear_cliente(self, llm: LLMFalso, tope: int = 10000) -> TestClient:
        cliente = TestClient(crear_app(self.ajustes(tope), llm))
        cliente.__enter__()
        self.addCleanup(cliente.__exit__, None, None, None)
        return cliente

    @staticmethod
    def eventos_sse(texto: str) -> set[str]:
        return {
            linea.partition(":")[2].strip()
            for linea in texto.splitlines()
            if linea.startswith("event:")
        }

    @staticmethod
    def datos_sse(texto: str) -> list[object]:
        datos = []
        for linea in texto.splitlines():
            if not linea.startswith("data:"):
                continue
            contenido = linea.partition(":")[2].strip()
            try:
                datos.append(json.loads(contenido))
            except json.JSONDecodeError:
                continue
        return datos

    @classmethod
    def contiene_modo_demo(cls, valor: object) -> bool:
        if isinstance(valor, dict):
            return valor.get("modo_demo") is True or any(
                cls.contiene_modo_demo(elemento) for elemento in valor.values()
            )
        if isinstance(valor, list):
            return any(cls.contiene_modo_demo(elemento) for elemento in valor)
        return False

    def guardar_semana(
        self, semana: int, incompleto: bool, con_reporte: bool = True
    ) -> None:
        repo = RepositorioHistorico(self.db_path)
        try:
            repo.cerrar_semana(
                semana, conteo_vacio(), incompleto, "2026-11-21T12:00:00", False
            )
            if con_reporte:
                repo.guardar_reporte(
                    semana, "2026-11-21T12:00:00",
                    f"reportes/semana_{semana:02d}.md", incompleto,
                )
        finally:
            repo.cerrar()

    def test_salud_devuelve_estado_ok(self):
        cliente = self.crear_cliente(LLMFalso([]))

        respuesta = cliente.get("/api/salud")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"estado": "ok"})

    def test_api_carga_la_simulacion_e03_y_el_clasificador_guardado(self):
        cliente = self.crear_cliente(LLMFalso([]))
        estado = cliente.app.state.estado

        self.assertIsInstance(estado.modelo, ClasificadorSentimiento)
        self.assertIsInstance(estado.entorno, EntornoHotel)
        self.assertEqual(estado.entorno.escenario.nombre, "E03 Dos incidentes")
        self.assertIs(estado.contexto().modelo, estado.modelo)
        self.assertIs(estado.contexto().entorno, estado.entorno)
        self.assertFalse(hasattr(estado, "repo_historico"))
        self.assertEqual(len(estado._trazas_demo), 3)
        self.assertEqual(
            estado.repo_demo.con.execute("SELECT COUNT(*) FROM semanas").fetchone()[0],
            14,
        )
        self.assertGreater(
            estado.repo_demo.con.execute("SELECT COUNT(*) FROM resenas").fetchone()[0],
            400,
        )
        self.assertTrue(
            estado.repo_demo.con.execute(
                "SELECT 1 FROM resenas WHERE id LIKE 'R%' LIMIT 1"
            ).fetchone()
        )
        self.assertTrue(
            estado.repo_demo.con.execute(
                "SELECT 1 FROM alertas WHERE semana = 8 AND tema = 'servicio' LIMIT 1"
            ).fetchone()
        )
        reportes = estado.repo_demo.reportes()
        self.assertEqual(len(reportes), 14)
        self.assertTrue(Path(reportes[0]["ruta"]).is_file())
        with closing(sqlite3.connect(self.db_path)) as con:
            ruta_persistida = con.execute(
                "SELECT ruta FROM reportes ORDER BY semana LIMIT 1"
            ).fetchone()[0]
        self.assertTrue(Path(ruta_persistida).is_absolute())
        self.assertTrue(Path(ruta_persistida).is_file())
        self.assertEqual(len(cliente.get("/api/semanas").json()), 14)

    def test_chat_sin_iniciar_stream_no_reserva_el_candado(self):
        cliente = self.crear_cliente(LLMFalso([]))
        estado = cliente.app.state.estado
        ruta_chat = next(
            ruta for ruta in crear_router(estado).routes
            if getattr(ruta, "path", None) == "/api/chat"
        )

        respuesta = ruta_chat.endpoint(
            solicitud=SolicitudChat(mensaje="consulta sin iniciar"),
            codigo=_CODIGO_PRUEBA,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(estado.candado.locked())

    def test_chat_rechaza_codigo_ausente_o_incorrecto_sin_invocar_llm(self):
        llm = LLMFalso([])
        cliente = self.crear_cliente(llm)

        sin_codigo = cliente.post("/api/chat", json={"mensaje": "consulta sintética"})
        codigo_incorrecto = cliente.post(
            "/api/chat",
            json={"mensaje": "consulta sintética"},
            headers={"X-Codigo-Acceso": "codigo-incorrecto"},
        )

        self.assertEqual(sin_codigo.status_code, 401)
        self.assertEqual(codigo_incorrecto.status_code, 401)
        self.assertEqual(llm.llamadas, [])

    def test_chat_rechaza_mensaje_vacio_o_mayor_a_2000_sin_procesarlo(self):
        llm = LLMFalso([])
        cliente = self.crear_cliente(llm)
        antes = cliente.get("/api/demo").text
        marcador = "INVALIDO_NO_REGISTRAR_"

        vacio = cliente.post(
            "/api/chat", json={"mensaje": ""}, headers=self.headers
        )
        largo = cliente.post(
            "/api/chat",
            json={"mensaje": marcador + ("x" * 2000)},
            headers=self.headers,
        )

        self.assertEqual(vacio.status_code, 422)
        self.assertEqual(largo.status_code, 422)
        self.assertEqual(llm.llamadas, [])
        self.assertEqual(cliente.get("/api/demo").text, antes)
        self.assertNotIn(marcador, cliente.get("/api/demo").text)

    def test_chat_sse_emite_paso_y_final_y_error_controlado(self):
        llm = LLMFalso([
            respuesta_texto("Respuesta sintética."),
            RuntimeError("fallo sintético privado"),
        ])
        cliente = self.crear_cliente(llm)

        final = cliente.post(
            "/api/chat", json={"mensaje": "hola"}, headers=self.headers
        )

        self.assertEqual(final.status_code, 200)
        self.assertIn("paso", self.eventos_sse(final.text))
        self.assertIn("final", self.eventos_sse(final.text))

        error = cliente.post(
            "/api/chat", json={"mensaje": "hola"}, headers=self.headers
        )

        self.assertEqual(error.status_code, 200)
        self.assertIn("error", self.eventos_sse(error.text))
        self.assertNotIn("Traceback", error.text)
        self.assertNotIn("fallo sintético privado", error.text)

    def test_chat_sse_no_transmite_credenciales_en_paso_final_ni_error(self):
        llm = LLMFalso([
            respuesta_herramienta(
                "contar_resenas",
                valor=f"{_API_KEY_PRUEBA} {_CODIGO_PRUEBA}",
            ),
            respuesta_texto(
                f"Respuesta con {_API_KEY_PRUEBA} {_CODIGO_PRUEBA}"
            ),
        ])
        cliente = self.crear_cliente(llm)
        respuesta = cliente.post(
            "/api/chat", json={"mensaje": "cuenta las reseñas"}, headers=self.headers
        )

        self.assertEqual(respuesta.status_code, 200)
        eventos = self.eventos_sse(respuesta.text)
        self.assertIn("paso", eventos)
        self.assertIn("final", eventos)
        contenido = json.dumps(self.datos_sse(respuesta.text), ensure_ascii=False)
        for secreto in (_API_KEY_PRUEBA, _CODIGO_PRUEBA):
            self.assertNotIn(secreto, contenido)

        llm_error = LLMFalso([
            RuntimeError(f"excepción con {_API_KEY_PRUEBA} {_CODIGO_PRUEBA}")
        ])
        cliente_error = self.crear_cliente(llm_error)
        error = cliente_error.post(
            "/api/chat", json={"mensaje": "consulta"}, headers=self.headers
        )

        self.assertEqual(error.status_code, 200)
        self.assertIn("error", self.eventos_sse(error.text))
        contenido_error = json.dumps(
            self.datos_sse(error.text), ensure_ascii=False
        )
        for secreto in (_API_KEY_PRUEBA, _CODIGO_PRUEBA):
            self.assertNotIn(secreto, contenido_error)

    def test_chat_concurrente_rechaza_segunda_peticion_y_sqlite_sigue_sana(self):
        iniciada = threading.Event()
        liberar = threading.Event()

        def responder_bloqueado(mensajes):
            self.assertTrue(mensajes)
            iniciada.set()
            liberar.wait(timeout=5)
            return respuesta_texto("Respuesta sintética.")

        llm = LLMFalso(responder_bloqueado)
        cliente = self.crear_cliente(llm)
        cliente.get("/api/salud")
        self.guardar_semana(7, incompleto=False)

        with ThreadPoolExecutor(max_workers=1) as executor:
            primera = executor.submit(
                cliente.post, "/api/chat",
                json={"mensaje": "primera consulta"}, headers=self.headers,
            )
            try:
                self.assertTrue(iniciada.wait(timeout=5))
                segunda = cliente.post(
                    "/api/chat",
                    json={"mensaje": "segunda consulta"},
                    headers=self.headers,
                )
                self.assertEqual(segunda.status_code, 429)
                self.assertIn("ocupado", segunda.text.lower())
            finally:
                liberar.set()
            self.assertEqual(primera.result(timeout=10).status_code, 200)

        self.assertEqual(len(llm.llamadas), 1)
        self.assertEqual(cliente.get("/api/semanas").status_code, 200)
        with closing(sqlite3.connect(self.db_path)) as con:
            self.assertEqual(
                con.execute("PRAGMA integrity_check").fetchone()[0], "ok"
            )

    def test_tope_diario_agotado_declara_modo_demo(self):
        respuesta = respuesta_texto("Respuesta sintética.")
        respuesta.uso = Uso(3, 0)
        cliente = self.crear_cliente(
            LLMFalso([respuesta, respuesta_texto("Respuesta demo sintética.")]),
            tope=3,
        )

        primera = cliente.post(
            "/api/chat", json={"mensaje": "primera consulta"}, headers=self.headers
        )
        segunda = cliente.post(
            "/api/chat",
            json={"mensaje": "¿Cuántas reseñas hubo en la semana 40?"},
            headers=self.headers,
        )

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertTrue(
            any(self.contiene_modo_demo(dato) for dato in self.datos_sse(segunda.text))
        )
        datos = self.datos_sse(segunda.text)
        final = next(
            dato for dato in datos
            if isinstance(dato, dict) and dato.get("traza_demo")
        )
        self.assertEqual(final["traza_demo"], "chat-consulta-semana-40")
        self.assertEqual(
            final["texto"],
            "No hay datos disponibles para la semana 40, así que no puedo determinar cuántas reseñas hubo.",
        )
        self.assertTrue(any(
            dato.get("traza", {}).get("herramienta") == "contar_resenas"
            for dato in datos if isinstance(dato, dict)
        ))

    def test_modo_demo_reproduce_chat_correspondiente_con_herramientas_y_respuesta(self):
        cliente = self.crear_cliente(LLMFalso([]), tope=1)
        estado = cliente.app.state.estado
        estado._tokens_dia = 1
        estado._indice_traza_demo = 2
        estado._trazas_demo = [
            {
                "id": "chat-conteo-semana-08",
                "pregunta": "¿Cuántas reseñas hubo en la semana 8?",
                "disparadores": ["cuantas resenas semana 8"],
                "herramientas": ["contar_resenas"],
                "eventos": [{
                    "fase": "ACCION", "evento": "herramienta",
                    "herramienta": "contar_resenas",
                    "argumentos": {"semana": 8},
                    "resultado": {"ok": True, "datos": {"total": 40}},
                }],
                "respuesta_final": "En la semana 8 hubo 40 reseñas.",
            },
            {
                "id": "chat-servicio-semana-08",
                "pregunta": "¿El servicio empeoró en la semana 8?",
                "disparadores": ["servicio empeoro semana 8"],
                "herramientas": ["comparar_semana"],
                "eventos": [{
                    "fase": "ACCION", "evento": "herramienta",
                    "herramienta": "comparar_semana",
                    "argumentos": {"semana": 8, "tema": "servicio"},
                    "resultado": {"ok": True, "datos": {"servicio": {"alarma": False}}},
                }],
                "respuesta_final": "El servicio empeoró en la semana 8.",
            },
            {
                "id": "chat-consulta-semana-40",
                "pregunta": "¿Cuántas reseñas hubo en la semana 40?",
                "disparadores": ["resenas semana 40"],
                "herramientas": ["contar_resenas"],
                "eventos": [{
                    "fase": "ACCION", "evento": "herramienta",
                    "herramienta": "contar_resenas",
                    "argumentos": {"semana": 40},
                    "resultado": {"ok": False, "error": "sin_datos"},
                }],
                "respuesta_final": "No hay datos para la semana 40.",
            },
        ]

        preguntas = (
            "¿Cuántas reseñas hubo en la semana 8?",
            "¿El servicio empeoró en la semana 8?",
            "¿Cuántas reseñas hubo en la semana 40?",
        )
        for pregunta, esperado in zip(
            preguntas,
            ("chat-conteo-semana-08", "chat-servicio-semana-08", "chat-consulta-semana-40"),
        ):
            respuesta = cliente.post(
                "/api/chat", json={"mensaje": pregunta}, headers=self.headers
            )
            datos = self.datos_sse(respuesta.text)
            self.assertEqual(respuesta.status_code, 200)
            final = next(item for item in datos if "texto" in item and "modo_demo" in item)
            self.assertEqual(final["traza_demo"], esperado)
            self.assertIn("paso", self.eventos_sse(respuesta.text))
            self.assertIn("final", self.eventos_sse(respuesta.text))
            self.assertTrue(any(
                item.get("traza", {}).get("evento") == "herramienta"
                and "resultado" in item["traza"]
                for item in datos if isinstance(item, dict)
            ))
            self.assertTrue(final["texto"])

        traza = cliente.get("/api/demo").json()["traza"]
        self.assertTrue(any(e.get("evento") == "respuesta_final" for e in traza))
        self.assertTrue(any(e.get("pregunta") == preguntas[-1] for e in traza))

    def test_desconexion_cancela_agente_sin_liberar_candado_antes_del_hilo(self):
        iniciado = threading.Event()
        continuar = threading.Event()
        llamadas = []

        def respuesta_bloqueada(_mensajes):
            llamadas.append(1)
            iniciado.set()
            continuar.wait(timeout=5)
            return respuesta_herramienta("contar_resenas", semana=8)

        cliente = self.crear_cliente(LLMFalso([
            respuesta_herramienta("contar_resenas", semana=8),
            respuesta_bloqueada,
        ]))
        estado = cliente.app.state.estado
        ruta_chat = next(
            ruta for ruta in crear_router(estado).routes
            if getattr(ruta, "path", None) == "/api/chat"
        )
        respuesta = ruta_chat.endpoint(
            solicitud=SolicitudChat(mensaje="¿Cuántas reseñas hubo en la semana 8?"),
            codigo=_CODIGO_PRUEBA,
        )
        cancel_event = respuesta._cancel_event

        async def simular_desconexion():
            solicitud_enviada = False
            desconectar = asyncio.Event()

            async def receive():
                nonlocal solicitud_enviada
                if not solicitud_enviada:
                    solicitud_enviada = True
                    return {"type": "http.request", "body": b"", "more_body": False}
                await desconectar.wait()
                return {"type": "http.disconnect"}

            async def send(_mensaje):
                return None

            scope = {
                "type": "http", "asgi": {"version": "3.0"},
                "http_version": "1.1", "method": "POST", "scheme": "http",
                "path": "/api/chat", "raw_path": b"/api/chat", "query_string": b"",
                "headers": [], "client": ("test", 123), "server": ("test", 80),
            }
            tarea = asyncio.create_task(respuesta(scope, receive, send))
            self.assertTrue(await asyncio.to_thread(iniciado.wait, 5))
            self.assertTrue(estado.candado.locked())
            desconectar.set()
            for _ in range(50):
                if cancel_event.is_set():
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(cancel_event.is_set())
            self.assertTrue(estado.candado.locked())
            continuar.set()
            await asyncio.wait_for(tarea, timeout=5)

        try:
            asyncio.run(simular_desconexion())
            for _ in range(50):
                if not estado.candado.locked():
                    break
                threading.Event().wait(0.01)
            self.assertFalse(estado.candado.locked())
            self.assertEqual(len(llamadas), 1)
        finally:
            continuar.set()

    def test_limite_total_detiene_stream_y_conserva_candado_hasta_terminar_hilo(self):
        iniciado = threading.Event()
        continuar = threading.Event()

        def respuesta_bloqueada(_mensajes):
            iniciado.set()
            continuar.wait(timeout=5)
            return respuesta_texto("Respuesta sintética.")

        cliente = self.crear_cliente(LLMFalso([respuesta_bloqueada]))
        estado = cliente.app.state.estado
        estado.ajustes.api_chat_timeout_s = 0.05
        ruta_chat = next(
            ruta for ruta in crear_router(estado).routes
            if getattr(ruta, "path", None) == "/api/chat"
        )
        respuesta = ruta_chat.endpoint(
            solicitud=SolicitudChat(mensaje="consulta"), codigo=_CODIGO_PRUEBA,
        )
        enviados = []

        async def simular():
            primera = True

            async def receive():
                nonlocal primera
                if primera:
                    primera = False
                    return {"type": "http.request", "body": b"", "more_body": False}
                await asyncio.Event().wait()

            async def send(mensaje):
                enviados.append(mensaje)

            scope = {
                "type": "http", "asgi": {"version": "3.0"},
                "http_version": "1.1", "method": "POST", "scheme": "http",
                "path": "/api/chat", "raw_path": b"/api/chat", "query_string": b"",
                "headers": [], "client": ("test", 123), "server": ("test", 80),
            }
            await respuesta(scope, receive, send)

        try:
            asyncio.run(simular())
            self.assertTrue(iniciado.is_set())
            self.assertTrue(respuesta._cancel_event.is_set())
            self.assertTrue(estado.candado.locked())
            texto_sse = b"".join(
                mensaje.get("body", b"") for mensaje in enviados
            ).decode()
            self.assertIn('"error": "limite_tiempo"', texto_sse)

            segunda = ruta_chat.endpoint(
                solicitud=SolicitudChat(mensaje="otra consulta"), codigo=_CODIGO_PRUEBA,
            )

            async def probar_bloqueo():
                respuestas = []

                async def receive():
                    return {"type": "http.request", "body": b"", "more_body": False}

                async def send(mensaje):
                    respuestas.append(mensaje)

                scope = {
                    "type": "http", "asgi": {"version": "3.0"},
                    "http_version": "1.1", "method": "POST", "scheme": "http",
                    "path": "/api/chat", "raw_path": b"/api/chat", "query_string": b"",
                    "headers": [], "client": ("test", 123), "server": ("test", 80),
                }
                await segunda(scope, receive, send)
                return respuestas

            bloqueada = asyncio.run(probar_bloqueo())
            self.assertEqual(bloqueada[0]["status"], 429)
        finally:
            continuar.set()
        for _ in range(100):
            if not estado.candado.locked():
                break
            threading.Event().wait(0.01)
        self.assertFalse(estado.candado.locked())

    def test_tope_diario_se_reinicia_en_un_nuevo_dia_utc(self):
        respuesta = respuesta_texto("Respuesta sintética.")
        respuesta.uso = Uso(1, 0)
        cliente = self.crear_cliente(LLMFalso([respuesta]), tope=1)

        resultado = cliente.post(
            "/api/chat", json={"mensaje": "consulta"}, headers=self.headers
        )
        estado = cliente.app.state.estado
        self.assertEqual(resultado.status_code, 200)
        self.assertTrue(estado.presupuesto_agotado())

        estado._dia_utc = date.min
        self.assertFalse(cliente.get("/api/demo").json()["modo_demo"])

    def test_secretos_no_aparecen_en_respuesta_traza_logs_ni_archivos(self):
        llm = LLMFalso([RuntimeError(f"{_API_KEY_PRUEBA} {_CODIGO_PRUEBA}")])
        cliente = self.crear_cliente(llm)
        capturador = _CapturadorLogs()
        logger = logging.getLogger()
        nivel_anterior = logger.level
        logger.addHandler(capturador)
        logger.setLevel(logging.DEBUG)
        try:
            respuesta = cliente.post(
                "/api/chat", json={"mensaje": "consulta segura"}, headers=self.headers
            )
            traza = cliente.get("/api/demo")
        finally:
            logger.removeHandler(capturador)
            logger.setLevel(nivel_anterior)

        contenido = "\n".join(
            (respuesta.text, traza.text, *capturador.registros)
        )
        for secreto in (_API_KEY_PRUEBA, _CODIGO_PRUEBA):
            self.assertFalse(secreto in contenido)
        self.assertNotIn("Traceback", contenido)
        for ruta in self.carpeta.rglob("*"):
            if ruta.is_file():
                contenido_archivo = ruta.read_bytes()
                for secreto in (_API_KEY_PRUEBA, _CODIGO_PRUEBA):
                    self.assertFalse(secreto.encode() in contenido_archivo)

    def test_cierre_y_reinicio_requieren_codigo_y_reinicio_restablece_simulacion(self):
        llm = LLMFalso([
            respuesta_herramienta("generar_reporte", semana=77),
            respuesta_texto("Reporte de la semana 77 generado."),
        ])
        cliente = self.crear_cliente(llm)
        estado = cliente.app.state.estado
        self.guardar_semana(77, incompleto=False)

        for headers in ({}, {"X-Codigo-Acceso": "codigo-incorrecto"}):
            cierre = cliente.post("/api/cierre", json={"semana": 77}, headers=headers)
            reinicio = cliente.post("/api/reiniciar", headers=headers)
            self.assertEqual(cierre.status_code, 401)
            self.assertEqual(reinicio.status_code, 401)
        self.assertEqual(llm.llamadas, [])
        repo = RepositorioHistorico(self.db_path)
        try:
            self.assertIsNotNone(repo.semana(77))
        finally:
            repo.cerrar()

        cierre_autorizado = cliente.post(
            "/api/cierre", json={"semana": 77}, headers=self.headers
        )
        self.assertEqual(cierre_autorizado.status_code, 200)

        reinicio_autorizado = cliente.post("/api/reiniciar", headers=self.headers)
        self.assertEqual(reinicio_autorizado.status_code, 200)
        self.assertEqual(
            estado.repo_demo.con.execute("SELECT COUNT(*) FROM semanas").fetchone()[0],
            14,
        )
        self.assertGreater(
            estado.repo_demo.con.execute("SELECT COUNT(*) FROM resenas").fetchone()[0],
            400,
        )
        self.assertIsNone(estado.repo_demo.semana(77))
        with closing(sqlite3.connect(self.db_path)) as con:
            self.assertEqual(
                con.execute("PRAGMA integrity_check").fetchone()[0], "ok"
            )
            existe_semana_prueba = con.execute(
                "SELECT 1 FROM semanas WHERE semana = 77"
            ).fetchone()
        self.assertIsNone(existe_semana_prueba)

    def test_demo_y_resultados_no_exponen_secretos_y_etiquetan_solo_existentes(self):
        cliente = self.crear_cliente(LLMFalso([]))
        cliente.get("/api/salud")
        self.guardar_semana(70, incompleto=True)
        self.guardar_semana(71, incompleto=False)
        self.guardar_semana(72, incompleto=False, con_reporte=False)

        demo = cliente.get("/api/demo")
        resultados = cliente.get("/api/resultados")

        self.assertEqual(demo.status_code, 200)
        self.assertEqual(resultados.status_code, 200)
        self.assertNotIn(_API_KEY_PRUEBA, demo.text)
        self.assertNotIn(_CODIGO_PRUEBA, demo.text)
        self.assertNotIn(_API_KEY_PRUEBA, resultados.text)
        self.assertNotIn(_CODIGO_PRUEBA, resultados.text)
        filas = resultados.json()
        self.assertIsInstance(filas, list)
        por_semana = {fila["semana"]: fila for fila in filas}
        self.assertIn(70, por_semana)
        self.assertIn(71, por_semana)
        self.assertNotIn(72, por_semana)
        self.assertTrue(any(valor == "provisional" for valor in por_semana[70].values()))
        self.assertTrue(any(valor == "final" for valor in por_semana[71].values()))


if __name__ == "__main__":
    unittest.main()
