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
  promedio REAL, s_max REAL, h REAL, enviada_en TEXT, tipo TEXT, mensaje TEXT);
CREATE TABLE IF NOT EXISTS alertas_legadas (alerta_id INTEGER PRIMARY KEY, p_valor REAL);
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
        columnas = {
            fila["name"]
            for fila in self.con.execute("PRAGMA table_info(alertas)")
        }

        with self.con:
            for columna in ("s_max", "h"):
                if columna not in columnas:
                    self.con.execute(
                        f"ALTER TABLE alertas ADD COLUMN {columna} REAL"
                    )

            if "p_valor" in columnas:
                self.con.execute(
                    "INSERT OR IGNORE INTO alertas_legadas (alerta_id, p_valor) "
                    "SELECT id, p_valor FROM alertas WHERE p_valor IS NOT NULL"
                )
                self.con.execute(
                    "ALTER TABLE alertas DROP COLUMN p_valor"
                )
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
        """Guarda CUSUM y preserva alertas antiguas por separado."""
        tiene_s = "s_max" in a
        tiene_h = "h" in a

        if tiene_s != tiene_h:
            raise ValueError("CUSUM requiere s_max y h.")

        if not tiene_s and "p_valor" not in a:
            raise ValueError("Falta el indicador estadistico.")

        with self.con:
            cursor = self.con.execute(
                """
                INSERT INTO alertas
                (semana, tema, proporcion, promedio, s_max, h,
                 enviada_en, tipo, mensaje)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    a["semana"], a["tema"],
                    a["proporcion"], a["promedio"],
                    a.get("s_max"), a.get("h"),
                    a["enviada_en"], a["tipo"], a["mensaje"],
                ),
            )

            if not tiene_s:
                self.con.execute(
                    "INSERT INTO alertas_legadas (alerta_id, p_valor) VALUES (?, ?)",
                    (cursor.lastrowid, a["p_valor"]),
                )

    def guardar_reporte(self, semana: int, ts: str, ruta: str, incompleto: bool):
        self.con.execute("INSERT OR REPLACE INTO reportes VALUES (?,?,?,?)", (semana, ts, ruta, int(incompleto)))
        self.con.commit()

    def conteos_diarios(
        self, semana: int, tema: str
    ) -> list[tuple[float, float]]:
        """Devuelve negativas y total ponderados de lunes a domingo."""

        dias = [(0.0, 0.0) for _ in range(7)]

        filas = self.con.execute(
            """
            SELECT
                substr(fecha, 1, 10) AS dia,
                SUM(
                    CASE WHEN polaridad = 'negativa'
                    THEN CASE WHEN revision_manual = 1
                              THEN 0.5 ELSE 1.0 END
                    ELSE 0.0 END
                ) AS negativas,
                SUM(
                    CASE WHEN revision_manual = 1
                         THEN 0.5 ELSE 1.0 END
                ) AS total
            FROM resenas
            WHERE semana = ? AND tema = ?
            GROUP BY substr(fecha, 1, 10)
            ORDER BY dia
            """,
            (semana, tema),
        ).fetchall()

        from datetime import date

        for fila in filas:
            fecha = date.fromisoformat(fila["dia"])
            indice = fecha.weekday()

            negativas, total = dias[indice]

            dias[indice] = (
                negativas + float(fila["negativas"]),
                total + float(fila["total"]),
            )

        return dias

    def conteos_semana(self, semana: int) -> dict:
        """Obtiene conteos ponderados por tema y polaridad."""

        conteos = conteo_vacio()

        filas = self.con.execute(
            """
            SELECT tema, polaridad,
                   SUM(
                       CASE WHEN revision_manual = 1
                            THEN 0.5 ELSE 1.0 END
                   ) AS cantidad
            FROM resenas
            WHERE semana = ?
            GROUP BY tema, polaridad
            """,
            (semana,),
        ).fetchall()

        for fila in filas:
            tema = fila["tema"]
            polaridad = fila["polaridad"]

            if tema in conteos and polaridad in conteos[tema]:
                conteos[tema][polaridad] = float(fila["cantidad"])

        return conteos

    def ejemplos_negativos(
        self,
        semana: int,
        tema: str,
        limite: int = 2,
    ) -> list[str]:
        """Recupera ejemplos negativos de una semana y tema."""

        if limite < 0:
            raise ValueError("El limite no puede ser negativo.")

        filas = self.con.execute(
            """
            SELECT texto
            FROM resenas
            WHERE semana = ?
              AND tema = ?
              AND polaridad = 'negativa'
            ORDER BY fecha, id
            LIMIT ?
            """,
            (semana, tema, limite),
        ).fetchall()

        return [fila["texto"] for fila in filas]

    # --- lectura (percepción del historial) ---
    def historial(self, antes_de: int, k: int, excluir_alertadas: bool = True) -> list[dict]:
        q = "SELECT * FROM semanas WHERE semana < ?" + (" AND alerto=0" if excluir_alertadas else "")
        filas = self.con.execute(q + " ORDER BY semana DESC LIMIT ?", (antes_de, k)).fetchall()
        return [dict(f, conteos=json.loads(f["conteos"])) for f in filas]

    def semana(self, semana: int) -> dict | None:
        f = self.con.execute("SELECT * FROM semanas WHERE semana=?", (semana,)).fetchone()
        return dict(f, conteos=json.loads(f["conteos"])) if f else None

    def alertas(self) -> list[dict]:
        return [dict(f) for f in self.con.execute(
            "SELECT a.*, l.p_valor AS p_valor FROM alertas a "
            "LEFT JOIN alertas_legadas l ON l.alerta_id = a.id ORDER BY a.id"
        )]

    def reportes(self) -> list[dict]:
        return [dict(f) for f in self.con.execute("SELECT * FROM reportes ORDER BY semana")]

    def resenas(self) -> list[dict]:
        return [dict(f) for f in self.con.execute("SELECT * FROM resenas ORDER BY fecha")]

    def descartadas(self) -> list[dict]:
        return [dict(f) for f in self.con.execute("SELECT * FROM descartadas")]
