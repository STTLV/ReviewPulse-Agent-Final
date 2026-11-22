"""Estado aislado de API, base sintética demo y presupuesto diario."""
from __future__ import annotations

import hmac
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from ..actuadores import GeneradorReporte, Notificador
from ..ciclo.ingesta import CONFIG_DEFECTO
from ..entorno import PLATAFORMAS
from ..herramientas.registro import Contexto, Sesion
from ..llm.cliente import ClienteLLM, ClienteOpenAI, RespuestaLLM
from ..memoria import RepositorioHistorico
from ..herramientas.analisis import construir_reporte
from ..config import Ajustes


class PresupuestoAgotado(Exception):
    """Señala que no debe iniciarse otra llamada al proveedor hoy."""


class _ClienteConPresupuesto:
    def __init__(self, estado: EstadoAPI, cliente: ClienteLLM):
        self.estado = estado
        self.cliente = cliente

    def chat(
        self, mensajes: list[dict], herramientas: list[dict] | None = None,
        modelo: str | None = None,
    ) -> RespuestaLLM:
        if self.estado.presupuesto_agotado():
            raise PresupuestoAgotado
        respuesta = self.cliente.chat(mensajes, herramientas=herramientas, modelo=modelo)
        uso = respuesta.uso
        if uso is not None:
            self.estado.registrar_tokens(uso.entrada, uso.salida)
        return respuesta


class _ModeloDemo:
    def predecir(self, textos: list[str]) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(polaridad="neutra", tema="servicio", confianza=0.5)
            for _ in textos
        ]


class _EntornoDemo:
    def disponible(self, plataforma: str, ahora: datetime) -> bool:
        return plataforma in PLATAFORMAS and ahora.tzinfo is not None


class EstadoAPI:
    def __init__(self, ajustes: Ajustes, llm: ClienteLLM | None = None):
        self.ajustes = ajustes
        self.proveedor = llm if llm is not None else ClienteOpenAI(ajustes)
        self.llm = _ClienteConPresupuesto(self, self.proveedor)
        self.candado = threading.Lock()
        self._presupuesto_lock = threading.Lock()
        self._traza_lock = threading.Lock()
        self._dia_utc = datetime.now(timezone.utc).date()
        self._tokens_dia = 0
        self._trazas: list[dict] = []

        raiz = Path(__file__).resolve().parents[3]
        demo_default = Path(tempfile.gettempdir()) / "reviewpulse-demo.sqlite3"
        historico_default = raiz / "data" / "historico.sqlite3"
        self.demo_path = Path(os.environ.get("REVIEWPULSE_DB_PATH", str(demo_default)))
        self.historico_path = Path(os.environ.get(
            "REVIEWPULSE_HISTORICO_DB_PATH", str(historico_default)
        ))
        if self.demo_path.resolve() == self.historico_path.resolve():
            raise ValueError("La base demo y el histórico deben ser archivos separados.")

        self.demo_path.parent.mkdir(parents=True, exist_ok=True)
        self.historico_path.parent.mkdir(parents=True, exist_ok=True)
        self.directorio_salida = self.demo_path.parent / f"{self.demo_path.stem}_salidas"
        self.directorio_salida.mkdir(parents=True, exist_ok=True)
        self.reportes = GeneradorReporte(self.directorio_salida)
        self.notificador = Notificador(
            self.directorio_salida, "gerente@hotelpiloto.co"
        )
        self.cfg = {**CONFIG_DEFECTO}
        self.repo_historico = RepositorioHistorico(self.historico_path)
        self.repo_demo = RepositorioHistorico(self.demo_path)
        self._inicializar_demo()

    def _inicializar_demo(self) -> None:
        existe = self.repo_demo.con.execute(
            "SELECT 1 FROM semanas LIMIT 1"
        ).fetchone()
        if existe:
            return

        fecha = "2026-01-05T12:00:00"
        reseñas = (
            ("DEMO-001", "Google", "La habitación estaba limpia.", 5, "positiva", "limpieza"),
            ("DEMO-002", "TripAdvisor", "El servicio fue amable.", 5, "positiva", "servicio"),
            ("DEMO-003", "Google", "La ubicación era conveniente.", 4, "positiva", "ubicacion"),
        )
        for id_, plataforma, texto, calificacion, polaridad, tema in reseñas:
            self.repo_demo.guardar_resena({
                "id": id_,
                "plataforma": plataforma,
                "fecha": fecha,
                "semana": 0,
                "texto": texto,
                "calificacion": calificacion,
                "polaridad": polaridad,
                "tema": tema,
                "confianza": 0.9,
                "revision_manual": False,
                "procesada_en": fecha,
            })
        self.repo_demo.con.commit()
        self.repo_demo.cerrar_semana(
            0, self.repo_demo.conteos_semana(0), False, fecha, False
        )
        construir_reporte(
            self.repo_demo, self.reportes, 0, datetime.fromisoformat(fecha),
            False, self.cfg,
        )

    def _rotar_dia_si_corresponde(self) -> None:
        hoy = datetime.now(timezone.utc).date()
        if hoy != self._dia_utc:
            self._dia_utc = hoy
            self._tokens_dia = 0

    def presupuesto_agotado(self) -> bool:
        with self._presupuesto_lock:
            self._rotar_dia_si_corresponde()
            return (
                self.ajustes.llm_tope_tokens_dia <= 0
                or self._tokens_dia >= self.ajustes.llm_tope_tokens_dia
            )

    def registrar_tokens(self, entrada: int, salida: int) -> None:
        with self._presupuesto_lock:
            self._rotar_dia_si_corresponde()
            self._tokens_dia += max(0, int(entrada or 0)) + max(0, int(salida or 0))

    def autorizado(self, codigo: str | None) -> bool:
        esperado = self.ajustes.app_codigo_acceso
        return bool(esperado and codigo) and hmac.compare_digest(
            esperado.encode("utf-8"), codigo.encode("utf-8")
        )

    def contexto(self) -> Contexto:
        return Contexto(
            self.repo_demo,
            _ModeloDemo(),
            _EntornoDemo(),
            self.notificador,
            self.reportes,
            dict(self.cfg),
            datetime.now(timezone.utc),
            Sesion(),
        )

    def agregar_evento(self, evento: dict) -> None:
        with self._traza_lock:
            self._trazas.append(dict(evento))
            del self._trazas[:-200]

    def traza_publica(self) -> list[dict]:
        with self._traza_lock:
            contenido = json.dumps(self._trazas, ensure_ascii=False)
            return json.loads(self.texto_seguro(contenido))

    def texto_seguro(self, texto: str) -> str:
        salida = str(texto)
        for secreto in (self.ajustes.llm_api_key, self.ajustes.app_codigo_acceso):
            if secreto:
                salida = salida.replace(secreto, "[oculto]")
        return salida

    def reiniciar_demo(self) -> None:
        for reporte in self.repo_demo.reportes():
            ruta = Path(reporte["ruta"])
            if not ruta.is_absolute():
                ruta = self.directorio_salida / ruta
            ruta = ruta.resolve()
            directorio_reportes = (self.directorio_salida / "reportes").resolve()
            try:
                ruta.relative_to(directorio_reportes)
            except ValueError:
                continue
            ruta.unlink(missing_ok=True)
            ruta.with_suffix(".json").unlink(missing_ok=True)

        self.repo_demo.cerrar()
        for ruta in (
            self.demo_path,
            Path(f"{self.demo_path}-wal"),
            Path(f"{self.demo_path}-shm"),
        ):
            ruta.unlink(missing_ok=True)
        self.repo_demo = RepositorioHistorico(self.demo_path)
        self._inicializar_demo()
        self.notificador.bandeja.unlink(missing_ok=True)
        with self._traza_lock:
            self._trazas.clear()

    def cerrar(self) -> None:
        self.repo_demo.cerrar()
        self.repo_historico.cerrar()
