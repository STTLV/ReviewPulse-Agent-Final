"""Pruebas de partición y manejo seguro del etiquetado gold."""
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import unicodedata

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "experiments"))
sys.path.insert(0, str(RAIZ / "src"))
from acuerdo import cohen_kappa, consolidar_gold  # noqa: E402
from preparar_gold import preparar_gold  # noqa: E402
from reviewpulse.corpus import FRASES, construir_corpus  # noqa: E402


def filas(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo))


def escribir(ruta: Path, registros: list[dict]) -> None:
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(registros[0]), lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(registros)


class PruebasGold(unittest.TestCase):
    def test_kappa_perfecto_y_azar(self):
        self.assertEqual(cohen_kappa(["a", "b"], ["a", "b"]), 1.0)
        self.assertEqual(cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]), 0.0)

    def test_kappa_constante_y_entradas_invalidas(self):
        self.assertEqual(cohen_kappa(["a"] * 5, ["a"] * 5), 1.0)
        with self.assertRaises(ValueError):
            cohen_kappa([], [])
        with self.assertRaises(ValueError):
            cohen_kappa(["a"], ["a", "b"])

    def test_muestra_sin_etiquetas_y_reparto(self):
        muestra = filas(RAIZ / "data/gold/muestra.csv")
        sara = filas(RAIZ / "data/gold/etiquetas_sara.csv")
        ellen = filas(RAIZ / "data/gold/etiquetas_ellen.csv")
        self.assertEqual(len(muestra), 120)
        self.assertEqual(set(muestra[0]), {"id", "texto"})
        self.assertEqual(len({r["id"] for r in muestra}), 120)
        self.assertEqual(len(sara), 75)
        self.assertEqual(len(ellen), 75)
        self.assertEqual({r["id"] for r in sara} & {r["id"] for r in ellen}, {r["id"] for r in muestra[:30]})
        self.assertEqual({r["id"] for r in sara} | {r["id"] for r in ellen}, {r["id"] for r in muestra})
        self.assertEqual({r["id"] for r in sara}, {r["id"] for r in muestra[:75]})
        self.assertEqual({r["id"] for r in ellen}, {r["id"] for r in muestra[:30]} | {r["id"] for r in muestra[75:]})
        self.assertEqual([r["texto"] for r in muestra], [r["texto"] for r in construir_corpus(120, 2026, "evaluacion", 0.10)])

    def test_no_incluye_frases_reservadas_para_entrenamiento(self):
        muestra = filas(RAIZ / "data/gold/muestra.csv")
        def normalizar(t):
            return "".join(c for c in unicodedata.normalize("NFD", t.casefold()) if unicodedata.category(c) != "Mn")
        frases_entrenamiento = [normalizar(frase) for por_tema in FRASES.values() for frases in por_tema.values() for i, frase in enumerate(frases) if i % 4 != 3]
        for r in muestra:
            texto = normalizar(r["texto"])
            self.assertFalse(any(frase in texto for frase in frases_entrenamiento), r["id"])

    def test_no_sobrescribe_etiquetas_humanas(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            reserva = raiz.parent / (raiz.name + "-reservada.csv")
            try:
                paths = preparar_gold(raiz, reserva=reserva)
                sara = filas(paths["sara"])
                sara[0]["polaridad"] = "positiva"
                sara[0]["tema"] = "limpieza"
                escribir(paths["sara"], sara)
                preparar_gold(raiz, reserva=reserva)
                self.assertEqual(filas(paths["sara"])[0]["polaridad"], "positiva")
            finally:
                reserva.unlink(missing_ok=True)

    def test_no_publica_gold_si_faltan_etiquetas(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            reserva = raiz.parent / (raiz.name + "-reservada.csv")
            try:
                preparar_gold(raiz, reserva)
                with self.assertRaisesRegex(RuntimeError, "Faltan"):
                    consolidar_gold(raiz)
                self.assertFalse((raiz / "data/gold/gold.csv").exists())
            finally:
                reserva.unlink(missing_ok=True)

    def test_solo_consolida_etiquetas_completas(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            reserva = raiz.parent / (raiz.name + "-reservada.csv")
            try:
                p = preparar_gold(raiz, reserva)
                for nombre in ("sara", "ellen"):
                    registros = filas(p[nombre])
                    for r in registros:
                        r["polaridad"], r["tema"] = "neutra", "precio"
                    escribir(p[nombre], registros)
                resultado = consolidar_gold(raiz)
                self.assertEqual(resultado["total"], 120)
                self.assertEqual(resultado["kappa_polaridad"], 1.0)
                self.assertEqual(len(filas(raiz / "data/gold/gold.csv")), 120)
            finally:
                reserva.unlink(missing_ok=True)

    def test_desacuerdos_exigen_conciliacion_humana(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            reserva = raiz.parent / (raiz.name + "-reservada.csv")
            try:
                p = preparar_gold(raiz, reserva)
                for nombre in ("sara", "ellen"):
                    registros = filas(p[nombre])
                    for r in registros:
                        r["polaridad"], r["tema"] = "neutra", "precio"
                    if nombre == "ellen":
                        registros[0]["polaridad"] = "positiva"
                    escribir(p[nombre], registros)
                with self.assertRaisesRegex(RuntimeError, "desacuerdos"):
                    consolidar_gold(raiz)
                self.assertFalse((raiz / "data/gold/gold.csv").exists())
                r = raiz / "data/gold/acuerdos_resueltos.csv"
                with r.open("a", encoding="utf-8") as f:
                    f.write("EVAL-001,neutra,precio,Consenso manual\n")
                self.assertEqual(consolidar_gold(raiz)["desacuerdos"], 1)
            finally:
                reserva.unlink(missing_ok=True)

    def test_rechaza_etiquetas_invalidas(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            reserva = raiz.parent / (raiz.name + "-reservada.csv")
            try:
                p = preparar_gold(raiz, reserva)
                for nombre in ("sara", "ellen"):
                    registros = filas(p[nombre])
                    for r in registros:
                        r["polaridad"], r["tema"] = "neutra", "precio"
                    if nombre == "sara":
                        registros[0]["tema"] = "otro"
                    escribir(p[nombre], registros)
                with self.assertRaisesRegex(ValueError, "inválida"):
                    consolidar_gold(raiz)
            finally:
                reserva.unlink(missing_ok=True)


    def test_gold_real_con_30_comunes_y_trazabilidad(self):
        muestra = filas(RAIZ / "data/gold/muestra.csv")
        sara = filas(RAIZ / "data/gold/etiquetas_sara.csv")
        ellen = filas(RAIZ / "data/gold/etiquetas_ellen.csv")
        gold = filas(RAIZ / "data/gold/gold.csv")
        s = {r["id"]: r for r in sara}
        e = {r["id"]: r for r in ellen}
        comunes = set(s) & set(e)
        self.assertEqual(len(gold), 120)
        self.assertEqual(len(s), 75)
        self.assertEqual(len(e), 75)
        self.assertEqual(len(comunes), 30)
        self.assertEqual(set(s) | set(e), {r["id"] for r in muestra})
        self.assertEqual([r["id"] for r in gold], [r["id"] for r in muestra])
        for i in comunes:
            self.assertEqual((s[i]["polaridad"], s[i]["tema"]),
                             (e[i]["polaridad"], e[i]["tema"]))
        for row, original in zip(gold, muestra):
            esperado = s[row["id"]] if row["id"] in s else e[row["id"]]
            self.assertEqual(row, esperado)
            self.assertEqual(row["texto"], original["texto"])
        resultado = consolidar_gold(RAIZ)
        self.assertEqual(resultado["comunes"], 30)
        self.assertEqual(resultado["kappa_polaridad"], 1.0)
        self.assertEqual(resultado["kappa_tema"], 1.0)

if __name__ == "__main__":
    unittest.main()
