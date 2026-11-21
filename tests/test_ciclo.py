"""Regresiones del cierre determinista y su resiliencia."""
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from reviewpulse.ciclo.cierre import ejecutar_simulacion, puede_cerrar
from reviewpulse.ciclo.ingesta import Ingesta, CONFIG_DEFECTO
from reviewpulse.memoria import RepositorioHistorico, conteo_vacio
from reviewpulse.entorno import inicio_semana
from reviewpulse.entorno import EntornoHotel, Escenario


class PruebaCiclo(unittest.TestCase):
    def test_puede_cerrar(self):
        cfg = {"margen_espera_h": 12, "plazo_reporte_h": 24, "intervalo_h": 6}
        self.assertFalse(puede_cerrar(6, True, cfg))
        self.assertTrue(puede_cerrar(12, True, cfg))
        self.assertFalse(puede_cerrar(12, False, cfg))
        self.assertTrue(puede_cerrar(19, False, cfg))

    def test_reporte_se_genera_si_el_manejador_falla(self):
        esc = Escenario("Falla del manejador", "Control", "falla", semanas=2, volumen_base=0)
        entorno = EntornoHotel(esc, 11)

        class ManejadorFallido:
            def al_alarmar(self, alarma, ahora):
                return None
            def al_cerrar(self, semana, ahora, incompleto):
                raise RuntimeError("proveedor no disponible")

        with tempfile.TemporaryDirectory() as tmp:
            resultado = ejecutar_simulacion(
                entorno, Path(tmp), modelo=object(),
                fabrica_manejador=lambda *args: ManejadorFallido(),
            )
            self.assertEqual(len(resultado["reportes"]), 2)
            texto = (Path(tmp) / "reportes" / "semana_00.md").read_text(encoding="utf-8")
            self.assertIn("sin análisis del agente", texto)
            logs = [json.loads(linea) for linea in
                    (Path(tmp) / "log_ejecucion.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(e["evento"] == "reporte_respaldo" for e in logs))

    def test_sqlite_y_log_cerrados_si_falla_ingesta(self):
        esc = Escenario("Falla en ingesta", "Control", "falla", semanas=1, volumen_base=0)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(Ingesta, "paso", side_effect=RuntimeError("error simulado")):
                with self.assertRaisesRegex(RuntimeError, "error simulado"):
                    ejecutar_simulacion(EntornoHotel(esc, 11), Path(tmp), modelo=object())
            db = Path(tmp) / "memoria.db"
            self.assertTrue(db.exists())
            # Una conexión abierta en Windows bloquearía esta eliminación.
            db.unlink()
            self.assertFalse(db.exists())

    def test_alerta_no_se_repite_en_semana_y_tema(self):
        repo = RepositorioHistorico(":memory:")
        try:
            for semana in range(3):
                conteos = conteo_vacio()
                conteos["limpieza"]["positiva"] = 9
                conteos["limpieza"]["negativa"] = 1
                repo.cerrar_semana(semana, conteos, False,
                                  inicio_semana(semana + 1).isoformat(), False)
            fecha = inicio_semana(3).isoformat()
            for i in range(10):
                repo.guardar_resena({
                    "id": f"T{i}", "plataforma": "Google", "fecha": fecha,
                    "semana": 3, "texto": "Habitación con problemas de limpieza",
                    "calificacion": 1, "polaridad": "negativa",
                    "tema": "limpieza", "confianza": 0.9,
                    "revision_manual": 0, "procesada_en": fecha,
                })
            repo.con.commit()
            esc = Escenario("Alarma única", "Control", "normal", semanas=4, volumen_base=0)
            ingesta = Ingesta(EntornoHotel(esc, 11), repo, object(), CONFIG_DEFECTO)
            alarmas = ingesta.alarmas_de_cierre(3)
            self.assertEqual(len(alarmas), 1)
            self.assertEqual(alarmas[0].tema, "limpieza")
            self.assertEqual(ingesta.alarmas_de_cierre(3), [])
        finally:
            repo.cerrar()

    def test_reporte_de_respaldo_si_manejador_devuelve_false(self):
        esc = Escenario("Manejador sin respuesta", "Control", "falla", semanas=1, volumen_base=0)
        class Falso:
            def al_alarmar(self, alarma, ahora):
                pass
            def al_cerrar(self, semana, ahora, incompleto):
                return False
        with tempfile.TemporaryDirectory() as tmp:
            res = ejecutar_simulacion(
                EntornoHotel(esc, 11), Path(tmp), modelo=object(),
                fabrica_manejador=lambda *_: Falso(),
            )
            self.assertEqual(len(res["reportes"]), 1)
            self.assertIn("sin análisis del agente", (
                Path(tmp) / "reportes" / "semana_00.md"
            ).read_text(encoding="utf-8"))

    def test_sin_resenas_las_semanas_se_reportan(self):
        esc = Escenario("Sin reseñas", "Control", "normal", semanas=2, volumen_base=0)
        with tempfile.TemporaryDirectory() as tmp:
            r = ejecutar_simulacion(EntornoHotel(esc, 11), Path(tmp), modelo=object())
            self.assertEqual(len(r["reportes"]), 2)
            self.assertEqual(len(r["resenas"]), 0)
            self.assertTrue((Path(tmp) / "reportes" / "semana_01.md").exists())
