"""Memoria del agente.

- Corto plazo (`MemoriaTrabajo`): conteos de las semanas aún abiertas.
- Largo plazo (`RepositorioHistorico`, SQLite): reseñas etiquetadas, agregados
  semanales, reportes y alertas. Es la base de la comparación y la trazabilidad.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from .corpus import TEMAS

ESQUEMA = """
CREATE TABLE IF NOT EXISTS resenas (
  id TEXT PRIMARY KEY, plataforma TEXT, fecha TEXT, semana INTEGER, texto TEXT,
  calificacion INTEGER, polaridad TEXT, tema TEXT, confianza REAL, revision_manual INTEGER,
  procesada_en TEXT);
CREATE TABLE IF NOT EXISTS descartadas (id TEXT PRIMARY KEY, motivo TEXT, procesada_en TEXT);
CREATE TABLE IF NOT EXISTS semanas (
  semana INTEGER PRIMARY KEY, total INTEGER, conteos TEXT, datos_incompletos INTEGER,
  reporte_en TEXT, alerto INTEGER DEFAULT 0, tardias INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS alertas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, semana INTEGER, tema TEXT, proporcion REAL,
  promedio REAL, p_valor REAL, enviada_en TEXT, tipo TEXT, mensaje TEXT);
CREATE TABLE IF NOT EXISTS reportes (semana INTEGER PRIMARY KEY, generado_en TEXT, ruta TEXT, incompleto INTEGER);
"""


def conteo_vacio() -> dict:
    return {t: {"positiva": 0.0, "negativa": 0.0, "neutra": 0.0} for t in TEMAS}


class MemoriaTrabajo:
    """Estado interno de corto plazo: conteos por semana abierta y reseñas por revisar."""

    def __init__(self):
        self.conteos = defaultdict(conteo_vacio)
        self.revision_manual = defaultdict(int)

    def sumar(self, semana: int, tema: str, polaridad: str, peso: float):
        self.conteos[semana][tema][polaridad] += peso

    def sacar(self, semana: int) -> dict:
        return self.conteos.pop(semana, conteo_vacio())


class RepositorioHistorico:
    def __init__(self, ruta: Path | str = ":memory:"):
        self.con = sqlite3.connect(str(ruta), check_same_thread=False)  # noqa
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)
        self._cerrado = False

    def cerrar(self):
        """Cierra la conexión SQLite, de forma idempotente.

        Es importante cerrar esta conexión antes de borrar carpetas temporales:
        en Windows, un archivo SQLite abierto puede impedir su eliminación.
        """
        if not self._cerrado:
            self.con.close()
            self._cerrado = True

    # --- escritura (actuadores) ---
    def guardar_resena(self, r: dict):
        self.con.execute("INSERT OR REPLACE INTO resenas VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (r["id"], r["plataforma"], r["fecha"], r["semana"], r["texto"], r["calificacion"],
                          r["polaridad"], r["tema"], r["confianza"], int(r["revision_manual"]), r["procesada_en"]))

    def guardar_descartada(self, id_: str, motivo: str, ts: str):
        self.con.execute("INSERT OR REPLACE INTO descartadas VALUES (?,?,?)", (id_, motivo, ts))

    def cerrar_semana(self, semana: int, conteos: dict, incompleto: bool, ts: str, alerto: bool):
        total = sum(sum(v.values()) for v in conteos.values())
        self.con.execute("INSERT OR REPLACE INTO semanas (semana,total,conteos,datos_incompletos,reporte_en,alerto)"
                         " VALUES (?,?,?,?,?,?)", (semana, round(total), json.dumps(conteos), int(incompleto),
                                                   ts, int(alerto)))
        self.con.commit()

    def ajustar_semana_tardia(self, semana: int, tema: str, polaridad: str, peso: float):
        fila = self.con.execute("SELECT conteos, tardias FROM semanas WHERE semana=?", (semana,)).fetchone()
        if not fila:
            return False
        c = json.loads(fila["conteos"])
        c[tema][polaridad] += peso
        self.con.execute("UPDATE semanas SET conteos=?, tardias=tardias+1, total=total+1 WHERE semana=?",
                         (json.dumps(c), semana))
        return True

    def marcar_alerta_semana(self, semana: int):
        self.con.execute("UPDATE semanas SET alerto=1 WHERE semana=?", (semana,))

    def guardar_alerta(self, a: dict):
        self.con.execute("INSERT INTO alertas (semana,tema,proporcion,promedio,p_valor,enviada_en,tipo,mensaje)"
                         " VALUES (?,?,?,?,?,?,?,?)", (a["semana"], a["tema"], a["proporcion"], a["promedio"],
                                                       a["p_valor"], a["enviada_en"], a["tipo"], a["mensaje"]))
        self.con.commit()

    def guardar_reporte(self, semana: int, ts: str, ruta: str, incompleto: bool):
        self.con.execute("INSERT OR REPLACE INTO reportes VALUES (?,?,?,?)", (semana, ts, ruta, int(incompleto)))
        self.con.commit()

    # --- lectura (percepción del historial) ---
    def historial(self, antes_de: int, k: int, excluir_alertadas: bool = True) -> list[dict]:
        q = "SELECT * FROM semanas WHERE semana < ?" + (" AND alerto=0" if excluir_alertadas else "")
        filas = self.con.execute(q + " ORDER BY semana DESC LIMIT ?", (antes_de, k)).fetchall()
        return [dict(f, conteos=json.loads(f["conteos"])) for f in filas]

    def semana(self, semana: int) -> dict | None:
        f = self.con.execute("SELECT * FROM semanas WHERE semana=?", (semana,)).fetchone()
        return dict(f, conteos=json.loads(f["conteos"])) if f else None

    def alertas(self) -> list[dict]:
        return [dict(f) for f in self.con.execute("SELECT * FROM alertas ORDER BY id")]

    def reportes(self) -> list[dict]:
        return [dict(f) for f in self.con.execute("SELECT * FROM reportes ORDER BY semana")]

    def resenas(self) -> list[dict]:
        return [dict(f) for f in self.con.execute("SELECT * FROM resenas ORDER BY fecha")]

    def descartadas(self) -> list[dict]:
        return [dict(f) for f in self.con.execute("SELECT * FROM descartadas")]
