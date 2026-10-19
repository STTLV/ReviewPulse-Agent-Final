"""Regresión del WinError 32 por conexión SQLite sin cerrar en Windows."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reviewpulse.agente import ReviewPulseAgent
from reviewpulse.entorno import EntornoHotel, Escenario


class PruebasLiberacionRecursos(unittest.TestCase):
    def _agente(self, ruta):
        # Entorno ligero. No modifica el modelo guardado ni las reglas de alerta.
        mini = Escenario("Control de recursos", "Entorno mínimo", "normal", semanas=1, volumen_base=0)
        return ReviewPulseAgent(EntornoHotel(mini, 101), Path(ruta), modelo=object())

    def test_cierra_log_y_sqlite_si_termina_correctamente(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._agente(tmp)
            res = a.ejecutar(horas_extra=24)
            self.assertEqual(set(res), {"alertas", "reportes", "resenas", "descartadas"})
            self.assertTrue(a.log.f.closed)
            with self.assertRaises(sqlite3.ProgrammingError):
                a.repo.con.execute("SELECT 1")
            self.assertTrue((Path(tmp) / "memoria.db").exists())
            self.assertTrue((Path(tmp) / "log_ejecucion.jsonl").exists())
        self.assertFalse(Path(tmp).exists())

    def test_cierra_log_y_sqlite_si_una_accion_falla(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._agente(tmp)
            with patch.object(a, "paso", side_effect=RuntimeError("error simulado")):
                with self.assertRaisesRegex(RuntimeError, "error simulado"):
                    a.ejecutar(horas_extra=24)
            self.assertTrue(a.log.f.closed)
            with self.assertRaises(sqlite3.ProgrammingError):
                a.repo.con.execute("SELECT 1")
        self.assertFalse(Path(tmp).exists())


if __name__ == "__main__":
    unittest.main()
