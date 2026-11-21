"""Ingesta de reseñas cada seis horas, con persistencia y CUSUM diario."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..corpus import TEMAS
from ..entorno import INICIO, PLATAFORMAS, EntornoHotel, PlataformaNoDisponible, semana_de
from ..herramientas.analisis import comparar_temas
from ..memoria import RepositorioHistorico
from ..modelo import ClasificadorSentimiento
from ..preprocesamiento import validar

CONFIG_DEFECTO: dict = {
    "umbral_confianza": 0.55,
    "cusum_delta": 0.25,
    "cusum_h": 4.0,
    "cusum_min_negativas": 6,
    "semanas_historial": 6,
    "min_semanas_historial": 3,
    "margen_espera_h": 12,
    "plazo_reporte_h": 24,
    "intervalo_h": 6,
    "destinatario": "gerente@hotelpiloto.co",
}


@dataclass(frozen=True)
class Alarma:
    semana: int
    tema: str
    tipo: str
    comparacion: dict


@dataclass
class ResultadoIngesta:
    disponibilidad: dict[str, bool]
    nuevas: int
    alarmas: list[Alarma] = field(default_factory=list)


class Ingesta:
    """Mantiene el cursor por plataforma y deriva conteos de SQLite."""

    def __init__(self, entorno: EntornoHotel, repo: RepositorioHistorico,
                 modelo: ClasificadorSentimiento, cfg: dict):
        self.entorno = entorno
        self.repo = repo
        self.modelo = modelo
        self.cfg = {**CONFIG_DEFECTO, **cfg}
        self.cursor = {plataforma: INICIO - timedelta(days=1) for plataforma in PLATAFORMAS}
        self.semanas_cerradas: set[int] = {
            fila["semana"] for fila in self.repo.con.execute("SELECT semana FROM semanas")
        }
        self._alarmas_emitidas: set[tuple[int, str]] = {
            (a["semana"], a["tema"]) for a in repo.alertas()
        }

    def paso(self, ahora: datetime) -> ResultadoIngesta:
        """Consulta, valida y clasifica. El cursor NO avanza si falla el conector."""
        lote: list[dict] = []
        disp: dict[str, bool] = {}
        for plataforma in PLATAFORMAS:
            try:
                nuevas = self.entorno.consultar(plataforma, self.cursor[plataforma], ahora)
            except PlataformaNoDisponible:
                disp[plataforma] = False
            else:
                disp[plataforma] = True
                lote.extend(nuevas)
                self.cursor[plataforma] = ahora

        validas: list[dict] = []
        for r in lote:
            ok, texto, motivo = validar(r)
            if ok:
                validas.append({**r, "texto": texto})
            else:
                self.repo.guardar_descartada(r["id"], motivo, ahora.isoformat())

        preds = self.modelo.predecir([r["texto"] for r in validas]) if validas else []
        if len(preds) != len(validas):
            raise ValueError("El clasificador devolvió un número incorrecto de predicciones.")

        semanas_afectadas: set[int] = set()
        tardias: set[int] = set()
        for r, p in zip(validas, preds):
            semana = semana_de(datetime.fromisoformat(r["fecha"]))
            if semana < 0:
                raise ValueError("La reseña es anterior al inicio del simulador.")
            manual = p.confianza < self.cfg["umbral_confianza"]
            fila = {
                **r,
                "semana": semana,
                "polaridad": p.polaridad,
                "tema": p.tema,
                "confianza": round(p.confianza, 4),
                "revision_manual": manual,
                "procesada_en": ahora.isoformat(),
            }
            self.repo.guardar_resena(fila)
            semanas_afectadas.add(semana)
            if semana in self.semanas_cerradas:
                tardias.add(semana)
                peso = 0.5 if manual else 1.0
                self.repo.ajustar_semana_tardia(semana, p.tema, p.polaridad, peso)

        self.repo.con.commit()
        alarmas: list[Alarma] = []
        for semana in sorted(semanas_afectadas):
            comp = comparar_temas(self.repo, semana, self.cfg)
            for tema in TEMAS:
                if comp[tema]["alarma"] and (semana, tema) not in self._alarmas_emitidas:
                    tipo = "tardia" if semana in tardias else "a_tiempo"
                    alarmas.append(Alarma(semana, tema, tipo, comp[tema]))
                    # Impide duplicados dentro de un mismo ciclo; quien maneja
                    # el evento guarda la alerta en SQLite.
                    self._alarmas_emitidas.add((semana, tema))

        return ResultadoIngesta(disp, len(validas), alarmas)

    def alarmas_de_cierre(self, semana: int) -> list[Alarma]:
        """Vuelve a evaluar una semana sin reseñas nuevas en el último paso."""
        comp = comparar_temas(self.repo, semana, self.cfg)
        nuevas = []
        for tema in TEMAS:
            if comp[tema]["alarma"] and (semana, tema) not in self._alarmas_emitidas:
                nuevas.append(Alarma(semana, tema, "a_tiempo", comp[tema]))
                self._alarmas_emitidas.add((semana, tema))
        return nuevas
