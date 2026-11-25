"""Tarea 11: interfaz y correcciones demo sin uso de red o tokens reales."""
from __future__ import annotations

import json
import threading
from types import SimpleNamespace
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from reviewpulse.api.estado import EstadoAPI
from reviewpulse.api.main import montar_interfaz
from reviewpulse.api.rutas import crear_router

ROOT = Path(__file__).resolve().parents[1]


class _EstadoSintetico:
    """Estado en memoria; no requiere SQLite, modelo entrenado ni proveedor."""

    def __init__(self):
        self._traza_lock = threading.Lock()
        self._trazas_demo = EstadoAPI._cargar_trazas_demo()
        self._indice_traza_demo = 0
        self.candado = threading.Lock()
        self.ajustes = SimpleNamespace(api_chat_timeout_s=120.0)
        self._eventos: list[dict] = []

    def siguiente_traza_demo(self, pregunta):
        return EstadoAPI.siguiente_traza_demo(self, pregunta)

    def autorizado(self, codigo):
        return codigo == "codigo-prueba-sintetico"

    def presupuesto_agotado(self):
        return True

    def agregar_evento(self, evento):
        self._eventos.append(evento)

    @staticmethod
    def texto_seguro(texto):
        return texto

    @staticmethod
    def traza_publica():
        return []


class PruebasInterfaz(unittest.TestCase):
    def test_inicio_y_recursos_se_sirven_sin_dependencias_externas(self):
        app = FastAPI()
        montar_interfaz(app)
        with TestClient(app) as client:
            inicio = client.get("/")
            self.assertEqual(inicio.status_code, 200)
            self.assertIn("text/html", inicio.headers["content-type"])
            self.assertIn("no-store", inicio.headers["cache-control"])
            self.assertIn("ReviewPulse", inicio.text)
            self.assertIn('id="chat-form"', inicio.text)
            self.assertIn('id="trace-list"', inicio.text)
            self.assertIn('type="password"', inicio.text)
            self.assertIn("Content-Security-Policy", inicio.headers)
            js = client.get("/assets/app.js")
            css = client.get("/assets/styles.css")
            self.assertEqual(js.status_code, 200)
            self.assertEqual(css.status_code, 200)
            self.assertIn("/api/chat", js.text)
            self.assertIn("response.body.getReader()", js.text)
            self.assertIn("@media(max-width:530px)", css.text)
            self.assertNotIn("localStorage.", js.text)
            self.assertNotIn("innerHTML", js.text)

    def test_tres_archivos_tienen_nombres_y_ids_coherentes(self):
        carpeta = ROOT / "data" / "trazas_demo"
        archivos = sorted(carpeta.glob("*.json"))
        self.assertEqual(
            [p.name for p in archivos],
            [
                "chat-consulta-semana-40.json",
                "chat-conteo-semana-08.json",
                "chat-servicio-semana-08.json",
            ],
        )
        for archivo in archivos:
            contenido = json.loads(archivo.read_text(encoding="utf-8"))
            self.assertEqual(contenido["id"], archivo.stem)
            self.assertTrue(contenido["respuesta_final"])
            self.assertTrue(contenido["herramientas"])

    def test_consulta_sin_coincidencia_recibe_aviso_explicito(self):
        app = FastAPI()
        estado = _EstadoSintetico()
        app.include_router(crear_router(estado))
        with TestClient(app) as client:
            response = client.post(
                "/api/chat", json={"mensaje": "hola"},
                headers={"X-Codigo-Acceso": "codigo-prueba-sintetico"},
            )
            self.assertEqual(response.status_code, 200)
            # Una consulta sin coincidencia no debe reproducir datos,
            # herramientas ni respuestas de la semana 8 por accidente.
            self.assertNotIn("event: paso", response.text)
            self.assertIn("event: final", response.text)
            eventos = [
                json.loads(line[5:].strip())
                for line in response.text.splitlines() if line.startswith("data:")
            ]
            self.assertEqual(len(eventos), 1)
            final = eventos[0]
            self.assertFalse(final["coincidencia_demo"])
            self.assertTrue(final["modo_demo"])
            self.assertIn("no hay una conversación grabada", final["texto"])
            self.assertIn("«hola»", final["texto"])
            self.assertIn("preguntas sugeridas", final["texto"])
            self.assertEqual(final["texto"], final["aviso_demo"])
            self.assertNotIn("traza_demo", final)
            self.assertNotIn("40 reseñas", response.text)
            self.assertEqual(estado._eventos, [])
            self.assertFalse(estado.candado.locked())

    def test_coincidencia_conserva_identidad_de_conversacion_y_final(self):
        app = FastAPI()
        estado = _EstadoSintetico()
        app.include_router(crear_router(estado))
        with TestClient(app) as client:
            for pregunta, identificador in (
                ("¿Cuántas reseñas hubo en la semana 8?", "chat-conteo-semana-08"),
                ("¿El servicio empeoró en la semana 8?", "chat-servicio-semana-08"),
                ("¿Cuántas reseñas hubo en la semana 40?", "chat-consulta-semana-40"),
            ):
                response = client.post(
                    "/api/chat", json={"mensaje": pregunta},
                    headers={"X-Codigo-Acceso": "codigo-prueba-sintetico"},
                )
                self.assertEqual(response.status_code, 200)
                events = [
                    json.loads(line[5:].strip())
                    for line in response.text.splitlines() if line.startswith("data:")
                ]
                final = next(x for x in events if "traza_demo" in x and "texto" in x)
                esperado = next(t for t in estado._trazas_demo if t["id"] == identificador)
                self.assertEqual(final["traza_demo"], identificador)
                self.assertTrue(final["coincidencia_demo"])
                self.assertEqual(final["texto"], esperado["respuesta_final"])
                self.assertFalse(estado.candado.locked())

    def test_chat_rechaza_codigo_invalido(self):
        app = FastAPI()
        app.include_router(crear_router(_EstadoSintetico()))
        with TestClient(app) as client:
            respuesta = client.post("/api/chat", json={"mensaje": "hola"})
            self.assertEqual(respuesta.status_code, 401)
