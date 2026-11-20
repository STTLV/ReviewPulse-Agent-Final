import unittest

from reviewpulse.herramientas.estadistica import (
    ParamsCusum,
    cusum_diario,
    p0_suavizado,
)


class TestEstadistica(unittest.TestCase):

    def setUp(self):
        self.P = ParamsCusum(
            delta=0.25,
            h=4.0,
            min_negativas=6
        )

    def test_alarma_el_dia_que_cruza_h(self):
        r = cusum_diario(
            [(0, 2), (3, 3), (3, 4)],
            0.2,
            self.P
        )
        self.assertTrue(r.alarma)
        self.assertEqual(r.dia_alarma, 2)
        self.assertAlmostEqual(r.s_max, 4.491, places=2)

    def test_no_alarma_sin_minimo_de_negativas(self):
        r = cusum_diario(
            [(0, 2), (3, 3), (3, 4)],
            0.2,
            ParamsCusum(0.25, 4.0, 7)
        )
        self.assertFalse(r.alarma)

    def test_s_nunca_es_negativo_y_dia_vacio_no_cambia(self):
        r = cusum_diario(
            [(0, 5), (0, 0)],
            0.2,
            self.P
        )
        self.assertEqual(r.serie, [0.0, 0.0])

    def test_p0_extremos_no_fallan(self):
        self.assertAlmostEqual(
            p0_suavizado(0, 0), 0.25
        )
        self.assertFalse(
            cusum_diario([(5, 5)], 0.97, self.P).alarma
        )
        self.assertFalse(
            cusum_diario([(0, 5)], 0.0, self.P).alarma
        )


    def test_conteos_diarios_con_revision_manual(self):
        from reviewpulse.memoria import RepositorioHistorico

        repo = RepositorioHistorico(":memory:")

        try:
            base = {
                "plataforma": "Google",
                "fecha": "2026-11-16",
                "semana": 1,
                "tema": "limpieza",
                "confianza": 0.9,
                "procesada_en": "2026-11-16T12:00:00",
                "calificacion": 3,
            }

            repo.guardar_resena({
                **base,
                "id": "R001",
                "texto": "Habitacion sucia",
                "polaridad": "negativa",
                "revision_manual": 1,
            })

            repo.guardar_resena({
                **base,
                "id": "R002",
                "texto": "Habitacion limpia",
                "polaridad": "positiva",
                "revision_manual": 0,
            })

            dias = repo.conteos_diarios(1, "limpieza")

            self.assertEqual(len(dias), 7)
            self.assertEqual(dias[0], (0.5, 1.5))
            self.assertEqual(dias[1:], [(0.0, 0.0)] * 6)

        finally:
            repo.cerrar()

    def test_conteos_semana_ponderados(self):
        from reviewpulse.memoria import RepositorioHistorico

        repo = RepositorioHistorico(":memory:")

        try:
            base = {
                "plataforma": "Google",
                "fecha": "2026-11-16",
                "semana": 1,
                "tema": "limpieza",
                "confianza": 0.9,
                "procesada_en": "2026-11-16T12:00:00",
                "calificacion": 3,
            }

            repo.guardar_resena({
                **base,
                "id": "R101",
                "texto": "Habitacion sucia",
                "polaridad": "negativa",
                "revision_manual": 1,
            })

            repo.guardar_resena({
                **base,
                "id": "R102",
                "texto": "Habitacion limpia",
                "polaridad": "positiva",
                "revision_manual": 0,
            })

            conteos = repo.conteos_semana(1)

            self.assertEqual(conteos["limpieza"]["negativa"], 0.5)
            self.assertEqual(conteos["limpieza"]["positiva"], 1.0)

        finally:
            repo.cerrar()

    def test_ejemplos_negativos_filtrados(self):
        from reviewpulse.memoria import RepositorioHistorico

        repo = RepositorioHistorico(":memory:")

        try:
            base = {
                "plataforma": "Google",
                "fecha": "2026-11-16",
                "semana": 1,
                "confianza": 0.9,
                "procesada_en": "2026-11-16T12:00:00",
                "calificacion": 2,
                "revision_manual": 0,
            }

            repo.guardar_resena({
                **base,
                "id": "R201",
                "texto": "Bano muy sucio",
                "polaridad": "negativa",
                "tema": "limpieza",
            })

            repo.guardar_resena({
                **base,
                "id": "R202",
                "texto": "Habitacion con polvo",
                "polaridad": "negativa",
                "tema": "limpieza",
            })

            repo.guardar_resena({
                **base,
                "id": "R203",
                "texto": "Servicio excelente",
                "polaridad": "positiva",
                "tema": "servicio",
            })

            ejemplos = repo.ejemplos_negativos(
                semana=1,
                tema="limpieza",
                limite=2
            )

            self.assertEqual(len(ejemplos), 2)
            self.assertEqual(
                ejemplos,
                ["Bano muy sucio", "Habitacion con polvo"]
            )

        finally:
            repo.cerrar()

    def test_guardar_alerta_cusum(self):
        from reviewpulse.memoria import RepositorioHistorico

        repo = RepositorioHistorico(":memory:")
        try:
            alerta = {
                "semana": 1,
                "tema": "limpieza",
                "proporcion": 0.70,
                "promedio": 0.20,
                "s_max": 4.75,
                "h": 4.0,
                "enviada_en": "2026-11-18T12:00:00",
                "tipo": "a_tiempo",
                "mensaje": "Alerta CUSUM de limpieza",
            }

            repo.guardar_alerta(alerta)
            guardadas = repo.alertas()

            self.assertEqual(len(guardadas), 1)
            self.assertAlmostEqual(guardadas[0]["s_max"], 4.75)
            self.assertAlmostEqual(guardadas[0]["h"], 4.0)
            self.assertIsNone(guardadas[0]["p_valor"])
        finally:
            repo.cerrar()

    def test_guardar_alerta_anterior(self):
        from reviewpulse.memoria import RepositorioHistorico

        repo = RepositorioHistorico(":memory:")
        try:
            alerta = {
                "semana": 1,
                "tema": "limpieza",
                "proporcion": 0.70,
                "promedio": 0.20,
                "p_valor": 0.01,
                "enviada_en": "2026-11-18T12:00:00",
                "tipo": "a_tiempo",
                "mensaje": "Alerta anterior",
            }

            repo.guardar_alerta(alerta)
            guardadas = repo.alertas()

            self.assertEqual(len(guardadas), 1)
            self.assertAlmostEqual(guardadas[0]["p_valor"], 0.01)
        finally:
            repo.cerrar()

    def test_notificador_cusum(self):
        from pathlib import Path
        from reviewpulse.actuadores import Notificador

        n = Notificador(Path("."), "gerente@hotelpiloto.co")

        alerta = {
            "semana": 1,
            "semana_texto": "01",
            "tema": "limpieza",
            "tipo": "a_tiempo",
            "proporcion": 0.75,
            "negativas": 9,
            "total": 12,
            "promedio": 0.20,
            "k": 6,
            "ejemplos": ["Habitacion sucia"],
            "s_max": 4.5,
            "h": 4.0,
        }

        mensaje = n.redactar(alerta)

        self.assertIn("CUSUM", mensaje)
        self.assertIn("S=4.500", mensaje)
        self.assertIn("h=4.000", mensaje)

    def test_reporte_incluye_nota(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from reviewpulse.actuadores import GeneradorReporte
        from reviewpulse.memoria import conteo_vacio

        with TemporaryDirectory() as carpeta:
            generador = GeneradorReporte(Path(carpeta))

            ruta = generador.generar(
                semana=1,
                semana_texto="01",
                conteos=conteo_vacio(),
                comparacion={},
                alertas=[],
                incompleto=False,
                revision_manual=0,
                ts="2026-11-18T12:00:00",
                nota="Diagnostico CUSUM verificado",
            )

            lineas = ruta.read_text(
                encoding="utf-8"
            ).splitlines()

            self.assertEqual(
                lineas[1],
                "Diagnostico CUSUM verificado"
            )

    def test_reporte_sin_nota_no_deja_linea_vacia(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from reviewpulse.actuadores import GeneradorReporte
        from reviewpulse.memoria import conteo_vacio

        with TemporaryDirectory() as carpeta:
            generador = GeneradorReporte(Path(carpeta))

            for nota in ("", "   "):
                with self.subTest(nota=nota):
                    ruta = generador.generar(
                        semana=1,
                        semana_texto="01",
                        conteos=conteo_vacio(),
                        comparacion={},
                        alertas=[],
                        incompleto=False,
                        revision_manual=0,
                        ts="2026-11-19T10:00:00",
                        nota=nota,
                    )

                    lineas = ruta.read_text(
                        encoding="utf-8"
                    ).splitlines()

                    self.assertTrue(
                        lineas[1].startswith("Generado:"),
                        lineas[:3],
                    )

if __name__ == "__main__":
    unittest.main()
