"""Contrato ReAct: decisiones, herramientas, trazabilidad y límites sin red."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from reviewpulse.actuadores import GeneradorReporte, Notificador
from reviewpulse.agente import (ManejadorAgente, MemoriaSesion, Traza, cifras_sin_respaldo,
                                extraer_cifras, resolver)
from reviewpulse.agente.prompts import PROMPT_SISTEMA, VERSION_PROMPT
from reviewpulse.ciclo.ingesta import CONFIG_DEFECTO
from reviewpulse.herramientas.registro import Contexto, Sesion
from reviewpulse.llm.cliente import LlamadaHerramienta, RespuestaLLM, Uso
from reviewpulse.llm.falso import LLMFalso, respuesta_herramienta, respuesta_texto
from reviewpulse.memoria import RepositorioHistorico


class ModeloFalso:
    def predecir(self, textos):
        return [SimpleNamespace(polaridad="negativa", tema="servicio", confianza=0.8) for _ in textos]


class EntornoFalso:
    def disponible(self, plataforma, ahora):
        return True


def llamada_invalida(nombre: str, crudo: str) -> RespuestaLLM:
    llamada = LlamadaHerramienta("herramienta-invalida", nombre, crudo)
    return RespuestaLLM(True, None, [llamada], Uso(1, 2),
                        mensaje_asistente={
                            "role": "assistant", "content": None,
                            "tool_calls": [{"id": llamada.id, "type": "function",
                                            "function": {"name": nombre, "arguments": crudo}}],
                        })


def llamada_con_uso(n: int) -> RespuestaLLM:
    r = respuesta_herramienta("estado_plataformas")
    r.uso = Uso(n, 0)
    return r


class PruebasBucle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = RepositorioHistorico(":memory:")
        self.addCleanup(self.repo.cerrar)
        self.ahora = datetime(2026, 3, 2, 15)
        for i, polaridad in enumerate(("negativa", "positiva"), 1):
            self.repo.guardar_resena({
                "id": f"r{i}", "plataforma": "Google",
                "fecha": f"2026-03-02T09:00:0{i}", "semana": 8,
                "texto": "Personal del hotel", "calificacion": 1 if i == 1 else 4,
                "polaridad": polaridad, "tema": "servicio", "confianza": 0.8,
                "revision_manual": False, "procesada_en": self.ahora.isoformat(),
            })
        self.repo.con.commit()
        carpeta = Path(self.tmp.name)
        self.ctx = Contexto(
            self.repo, ModeloFalso(), EntornoFalso(),
            Notificador(carpeta, "test@example.invalid"), GeneradorReporte(carpeta),
            CONFIG_DEFECTO.copy(), self.ahora, Sesion(),
        )

    def test_usa_herramienta_y_responde(self):
        llm = LLMFalso([respuesta_herramienta("contar_resenas", semana=8),
                        respuesta_texto("Hubo 2 reseñas en la semana 8.")])
        r = resolver("¿Cuántas reseñas hubo en la semana 8?", llm, self.ctx)
        self.assertTrue(r.ok, r)
        self.assertEqual(r.pasos, 2)
        self.assertEqual(r.cifras_sin_respaldo, [])
        self.assertEqual(len(llm.llamadas), 2)
        self.assertTrue(any(m.get("role") == "tool" for m in llm.llamadas[-1]))

    def test_cifra_inventada_se_corrige_una_vez_y_se_marca(self):
        llm = LLMFalso([respuesta_texto("Hubo 999 reseñas."),
                        respuesta_texto("Hubo 999 reseñas.")])
        r = resolver("¿Cuántas reseñas hubo?", llm, self.ctx)
        self.assertTrue(r.ok)
        self.assertEqual(r.cifras_sin_respaldo, ["999"])
        self.assertIn("cifra sin respaldo", r.texto)
        self.assertEqual(r.pasos, 2)

    def test_una_correccion_si_el_modelo_rectifica(self):
        llm = LLMFalso([respuesta_texto("Hay 999 reseñas."),
                        respuesta_herramienta("contar_resenas", semana=8),
                        respuesta_texto("Se registraron 2 reseñas.")])
        r = resolver("¿Cuántas reseñas hubo?", llm, self.ctx)
        self.assertTrue(r.ok)
        self.assertEqual(r.cifras_sin_respaldo, [])
        self.assertEqual(r.pasos, 3)

    def test_limite_de_pasos(self):
        llm = LLMFalso([lambda _: respuesta_herramienta("estado_plataformas") for _ in range(5)])
        self.assertEqual(resolver("x", llm, self.ctx, max_pasos=3).motivo, "limite_de_pasos")

    def test_limite_de_tokens(self):
        llm = LLMFalso([llamada_con_uso(50000)])
        r = resolver("x", llm, self.ctx)
        self.assertEqual(r.motivo, "limite_de_tokens")
        self.assertEqual(r.uso.entrada, 50000)
        self.assertFalse(any(e.get("evento") == "herramienta" for e in r.eventos))

    def test_fallo_del_proveedor_no_lanza(self):
        llm = LLMFalso([RespuestaLLM(False, None, [], Uso(0, 0), "proveedor", {})])
        self.assertEqual(resolver("x", llm, self.ctx).motivo, "proveedor")

    def test_excepcion_llm_no_lanza(self):
        llm = LLMFalso([RuntimeError("mensaje secreto en servidor")])
        r = resolver("x", llm, self.ctx)
        self.assertFalse(r.ok)
        self.assertNotIn("secreto en servidor", json.dumps(r.eventos))

    def test_error_de_herramienta_vuelve_al_modelo(self):
        llm = LLMFalso([llamada_invalida("contar_resenas", "{mal"),
                        respuesta_texto("No pude consultar.")])
        r = resolver("x", llm, self.ctx)
        self.assertTrue(r.ok)
        self.assertEqual(json.loads(llm.llamadas[-1][-1]["content"])["error"], "argumentos_invalidos")

    def test_sin_datos_no_inventa_ceros(self):
        llm = LLMFalso([respuesta_herramienta("contar_resenas", semana=40),
                        respuesta_texto("No hay datos de la semana 40.")])
        r = resolver("semana 40", llm, self.ctx)
        self.assertTrue(r.ok)
        self.assertIn("sin_datos", llm.llamadas[-1][-1]["content"])

    def test_porcentaje_coincide_con_proporcion(self):
        self.assertEqual(cifras_sin_respaldo("Subió al 70 %", ['{"proporcion": 0.7}']), [])
        self.assertEqual(cifras_sin_respaldo("Hubo 999 reseñas", []), ["999"])
        self.assertEqual(cifras_sin_respaldo("Hubo 1.234 reseñas", ['{"total": 1234}']), [])
        self.assertEqual(extraer_cifras("Hubo 5,5% y 12 casos"), ["5,5%", "12"])
        self.assertEqual(cifras_sin_respaldo("Se perdieron -5", ["saldo: 5"]), ["-5"])

    def test_redondeo_decimal_respaldado(self):
        self.assertEqual(cifras_sin_respaldo("CUSUM s_max 5,1", ['{"s_max":5.1234}']), [])
        self.assertEqual(cifras_sin_respaldo("CUSUM s_max 5.1", ['{"s_max":5.1234}']), [])
        self.assertEqual(cifras_sin_respaldo("CUSUM s_max 5,3", ['{"s_max":5.1234}']), ["5,3"])

    def test_porcentaje_redondeado_respaldado(self):
        self.assertEqual(cifras_sin_respaldo("Proporción 24,6 %", ['{"proporcion":0.2459}']), [])
        self.assertEqual(cifras_sin_respaldo("Proporción 24.6%", ['{"proporcion":0.2459}']), [])
        self.assertEqual(cifras_sin_respaldo("Proporción 24,7 %", ['{"proporcion":0.2459}']), ["24,7 %"])
        self.assertEqual(cifras_sin_respaldo("Proporción 26 %", ['{"proporcion":0.2459}']), ["26 %"])

    def test_prompt_identifica_hotel_piloto(self):
        self.assertIn("Hotel piloto", PROMPT_SISTEMA)
        self.assertNotIn("hotel ReviewPulse", PROMPT_SISTEMA)

    def test_traza_no_contiene_la_llave(self):
        self.ctx.cfg["llm_api_key"] = "secreta"
        ruta = Path(self.tmp.name) / "trazas" / "agente.jsonl"
        traza = Traza(ruta)
        r = resolver("x", LLMFalso([respuesta_texto("listo")]), self.ctx, traza=traza)
        self.assertTrue(r.ok)
        self.assertNotIn("secreta", json.dumps(r.eventos))
        self.assertNotIn("secreta", ruta.read_text(encoding="utf-8"))
        traza.evento("SISTEMA", "registro", api_key="sk-abcdefghij")
        self.assertNotIn("sk-abcdefghij", ruta.read_text(encoding="utf-8"))

    def test_memoria_copia_y_prompt_versionado(self):
        memoria = MemoriaSesion(PROMPT_SISTEMA)
        msg = {"role": "user", "content": "hola"}
        memoria.agregar(msg)
        msg["content"] = "adulterado"
        self.assertEqual(memoria.mensajes[-1]["content"], "hola")
        self.assertEqual(VERSION_PROMPT, "v1")

    def test_eventos_y_uso_acumulados(self):
        r1 = respuesta_herramienta("contar_resenas", semana=8)
        r1.uso = Uso(10, 5)
        r2 = respuesta_texto("2 reseñas en semana 8")
        r2.uso = Uso(20, 6)
        eventos = []
        r = resolver("semana 8", LLMFalso([r1, r2]), self.ctx, al_evento=eventos.append)
        self.assertEqual((r.uso.entrada, r.uso.salida), (30, 11))
        self.assertEqual(eventos, r.eventos)
        self.assertTrue(any(e.get("fase") == "ACCION" for e in r.eventos))

    def test_reseñas_no_pueden_dar_instrucciones(self):
        llm = LLMFalso([respuesta_herramienta("buscar_resenas", semana=8, limite=1),
                        respuesta_texto("He consultado las reseñas.")])
        r = resolver("Muestra una reseña", llm, self.ctx)
        self.assertTrue(r.ok)
        self.assertIn("<resena>", llm.llamadas[-1][-1]["content"])

    def test_manejador_con_falso_operativo_cierra_sin_respaldo(self):
        from reviewpulse.llm.falso import guion_operativo
        manejador = ManejadorAgente(LLMFalso([guion_operativo] * 8), lambda ahora: self.ctx)
        self.assertTrue(manejador.al_cerrar(8, self.ahora, False))
        self.assertEqual(len(self.repo.reportes()), 1)

    def test_manejador_cierre_exige_reporte_real(self):
        manejador = ManejadorAgente(LLMFalso([respuesta_texto("Listo")]), lambda ahora: self.ctx)
        self.assertFalse(manejador.al_cerrar(8, self.ahora, False))
        sin_parametros = ManejadorAgente(LLMFalso([respuesta_texto("Listo")]), lambda: self.ctx)
        self.assertFalse(sin_parametros.al_cerrar(8, self.ahora, False))
        manejador = ManejadorAgente(LLMFalso([respuesta_herramienta("generar_reporte", semana=8),
                                             respuesta_texto("Reporte generado.")]),
                                   lambda ahora: self.ctx)
        self.assertTrue(manejador.al_cerrar(8, self.ahora, False))

    def test_manejador_alarma_sin_alerta_provoca_fallback(self):
        manejador = ManejadorAgente(LLMFalso([respuesta_texto("Listo")]), lambda ahora: self.ctx)
        with self.assertRaisesRegex(RuntimeError, "no emitió"):
            manejador.al_alarmar(SimpleNamespace(semana=8, tema="servicio"), self.ahora)


if __name__ == "__main__":
    unittest.main()
