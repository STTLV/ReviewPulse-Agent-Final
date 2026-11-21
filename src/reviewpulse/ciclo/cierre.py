"""Cierre semanal robusto: ninguna caída del agente impide el reporte."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Protocol

from ..actuadores import GeneradorReporte, Notificador
from ..entorno import INICIO, EntornoHotel, inicio_semana, semana_de
from ..herramientas.analisis import construir_reporte, registrar_alerta
from ..memoria import RepositorioHistorico
from ..modelo import ClasificadorSentimiento
from .ingesta import Alarma, CONFIG_DEFECTO, Ingesta


class Manejador(Protocol):
    def al_alarmar(self, alarma: Alarma, ahora: datetime) -> None: ...
    def al_cerrar(self, semana: int, ahora: datetime, incompleto: bool) -> bool: ...


class ManejadorDeterminista:
    """Manejador operativo sin dependencia del LLM."""

    def __init__(self, repo: RepositorioHistorico, notificador: Notificador,
                 reportes: GeneradorReporte, cfg: dict):
        self.repo, self.notificador, self.reportes, self.cfg = repo, notificador, reportes, cfg

    def al_alarmar(self, alarma: Alarma, ahora: datetime) -> None:
        registrar_alerta(
            self.repo, self.notificador, alarma.semana, alarma.tema,
            alarma.comparacion, ahora, alarma.tipo,
        )

    def al_cerrar(self, semana: int, ahora: datetime, incompleto: bool) -> bool:
        construir_reporte(self.repo, self.reportes, semana, ahora, incompleto, self.cfg)
        return True


def puede_cerrar(horas: float, todas_disponibles: bool, cfg: dict) -> bool:
    """Espera 12 h, o cierra en el último ciclo antes de incumplir 24 h."""
    if horas < 0:
        return False
    if horas >= cfg["margen_espera_h"] and todas_disponibles:
        return True
    return horas + cfg["intervalo_h"] > cfg["plazo_reporte_h"]


class CierreSemanal:
    def __init__(self, ingesta: Ingesta, repo: RepositorioHistorico,
                 manejador: Manejador, reportes: GeneradorReporte,
                 cfg: dict, log: Callable):
        self.ingesta, self.repo, self.manejador = ingesta, repo, manejador
        self.reportes, self.cfg, self.log = reportes, cfg, log

    def procesar_alarma(self, alarma: Alarma, ahora: datetime) -> None:
        """No convierte un fallo del razonador en pérdida de la alerta."""
        try:
            self.manejador.al_alarmar(alarma, ahora)
            self.log(ahora, "ACCION", "alerta", semana=alarma.semana, tema=alarma.tema,
                     tipo=alarma.tipo)
        except Exception as exc:
            # El manejador LLM es opcional. El aviso determinista debe funcionar.
            if not isinstance(self.manejador, ManejadorDeterminista):
                fallback = ManejadorDeterminista(
                    self.repo, Notificador(self.reportes.carpeta.parent, self.cfg["destinatario"]),
                    self.reportes, self.cfg,
                )
                fallback.al_alarmar(alarma, ahora)
            else:
                raise
            self.log(ahora, "SISTEMA", "fallback_alerta", motivo=type(exc).__name__)

    def paso(self, ahora: datetime, disponibilidad: dict[str, bool]) -> None:
        actual = semana_de(ahora)
        for semana in range(actual):
            if semana in self.ingesta.semanas_cerradas:
                continue
            horas = (ahora - inicio_semana(semana + 1)).total_seconds() / 3600
            if not puede_cerrar(horas, all(disponibilidad.values()), self.cfg):
                continue
            for alarma in self.ingesta.alarmas_de_cierre(semana):
                self.procesar_alarma(alarma, ahora)
            incompleto = not all(disponibilidad.values())
            bien = False
            try:
                bien = self.manejador.al_cerrar(semana, ahora, incompleto) is True
            except Exception as exc:
                self.log(ahora, "SISTEMA", "fallo_manejador_cierre",
                         semana=semana, motivo=type(exc).__name__)
            if not bien:
                construir_reporte(
                    self.repo, self.reportes, semana, ahora, incompleto,
                    self.cfg, nota="Reporte generado sin análisis del agente.",
                )
                self.log(ahora, "SISTEMA", "reporte_respaldo", semana=semana)
            alerto = any(a["semana"] == semana for a in self.repo.alertas())
            self.repo.cerrar_semana(
                semana, self.repo.conteos_semana(semana), incompleto,
                ahora.isoformat(), alerto,
            )
            self.ingesta.semanas_cerradas.add(semana)
            self.log(ahora, "ACCION", "cierre_semana", semana=semana,
                     incompleto=incompleto, respaldo=not bien)


class Bitacora:
    """Log de cada paso; se cierra incluso durante errores de SQLite/ingesta."""

    def __init__(self, ruta: Path):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self.f = ruta.open("w", encoding="utf-8")

    def __call__(self, ahora: datetime, fase: str, evento: str, **datos):
        registro = {
            "ts_real": datetime.now().isoformat(timespec="milliseconds"),
            "ts_simulado": ahora.isoformat(),
            "fase": fase,
            "evento": evento,
            **datos,
        }
        self.f.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")

    def cerrar(self):
        if not self.f.closed:
            self.f.close()


def ejecutar_simulacion(
    entorno: EntornoHotel,
    carpeta: Path,
    cfg: dict | None = None,
    modelo=None,
    fabrica_manejador=None,
    horas_extra: int = 48,
) -> dict:
    """Ejecuta el ciclo y cierra SQLite y log aun si `Ingesta.paso` falla."""
    cfg = {**CONFIG_DEFECTO, **(cfg or {})}
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    repo = RepositorioHistorico(carpeta / "memoria.db")
    log = None
    try:
        log = Bitacora(carpeta / "log_ejecucion.jsonl")
        clasificador = modelo if modelo is not None else ClasificadorSentimiento.cargar()
        ingesta = Ingesta(entorno, repo, clasificador, cfg)
        notificador = Notificador(carpeta, cfg["destinatario"])
        reportes = GeneradorReporte(carpeta)
        manejador = (
            fabrica_manejador(repo, notificador, reportes, cfg)
            if fabrica_manejador is not None
            else ManejadorDeterminista(repo, notificador, reportes, cfg)
        )
        cierre = CierreSemanal(ingesta, repo, manejador, reportes, cfg, log)
        fin = inicio_semana(entorno.escenario.semanas) + timedelta(hours=horas_extra)
        ahora = INICIO + timedelta(hours=cfg["intervalo_h"])
        t0 = time.perf_counter()
        while ahora <= fin:
            r = ingesta.paso(ahora)
            log(ahora, "PERCEPCION", "ingesta", disponibilidad=r.disponibilidad,
                nuevas=r.nuevas)
            for alarma in r.alarmas:
                cierre.procesar_alarma(alarma, ahora)
            cierre.paso(ahora, r.disponibilidad)
            ahora += timedelta(hours=cfg["intervalo_h"])
        log(ahora, "SISTEMA", "fin_ejecucion",
            segundos=round(time.perf_counter() - t0, 2))
        return {
            "alertas": repo.alertas(),
            "reportes": repo.reportes(),
            "resenas": repo.resenas(),
            "descartadas": repo.descartadas(),
        }
    finally:
        try:
            if log is not None:
                log.cerrar()
        finally:
            repo.cerrar()
