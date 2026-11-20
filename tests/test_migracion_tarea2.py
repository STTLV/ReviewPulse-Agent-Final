import sqlite3
from contextlib import closing
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from reviewpulse.memoria import RepositorioHistorico


class TestMigracionTarea2(unittest.TestCase):

    def test_preserva_alertas_anteriores(self):
        with TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "historial.sqlite"

            with closing(sqlite3.connect(ruta)) as con, con:
                con.execute("""
                    CREATE TABLE alertas (
                        id INTEGER PRIMARY KEY,
                        semana INTEGER, tema TEXT,
                        proporcion REAL, promedio REAL,
                        p_valor REAL, enviada_en TEXT,
                        tipo TEXT, mensaje TEXT
                    )
                """)
                con.execute("""
                    INSERT INTO alertas VALUES
                    (1, 1, 'limpieza', 0.7, 0.2,
                     0.015, '2026-11-18', 'a_tiempo', 'Anterior')
                """)

            for _ in range(2):
                repo = RepositorioHistorico(ruta)
                try:
                    columnas = {
                        f["name"] for f in repo.con.execute(
                            "PRAGMA table_info(alertas)"
                        )
                    }
                    self.assertNotIn("p_valor", columnas)
                    self.assertIn("s_max", columnas)
                    self.assertIn("h", columnas)
                    alertas = repo.alertas()
                    self.assertEqual(len(alertas), 1)
                    self.assertAlmostEqual(
                        alertas[0]["p_valor"], 0.015
                    )
                finally:
                    repo.cerrar()

    def test_conteos_del_domingo(self):
        repo = RepositorioHistorico(":memory:")
        try:
            repo.guardar_resena({
                "id": "D001",
                "plataforma": "Google",
                "fecha": "2026-11-22",
                "semana": 1,
                "texto": "Habitacion sucia",
                "calificacion": 1,
                "polaridad": "negativa",
                "tema": "limpieza",
                "confianza": 0.4,
                "revision_manual": 1,
                "procesada_en": "2026-11-22T12:00:00",
            })

            dias = repo.conteos_diarios(1, "limpieza")

            self.assertEqual(len(dias), 7)
            self.assertEqual(dias[:6], [(0.0, 0.0)] * 6)
            self.assertEqual(dias[6], (0.5, 0.5))
        finally:
            repo.cerrar()