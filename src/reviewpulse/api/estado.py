"""Estado aislado de API, base sintética demo y presupuesto diario."""
from __future__ import annotations

import hmac
import json
import os
import shutil
import sqlite3
import tempfile
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from ..actuadores import GeneradorReporte, Notificador
from ..ciclo.cierre import ejecutar_simulacion
from ..ciclo.ingesta import CONFIG_DEFECTO
from ..entorno import EntornoHotel
from ..escenarios import ESCENARIOS
from ..herramientas.registro import Contexto, Sesion
from ..llm.cliente import ClienteLLM, ClienteOpenAI, RespuestaLLM
from ..memoria import RepositorioHistorico
from ..config import Ajustes
from ..modelo import ClasificadorSentimiento


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


class EstadoAPI:
    def __init__(self, ajustes: Ajustes, llm: ClienteLLM | None = None):
        self.ajustes = ajustes
        self.proveedor = llm if llm is not None else ClienteOpenAI(ajustes)
        self.llm = _ClienteConPresupuesto(self, self.proveedor)
        self.modelo = ClasificadorSentimiento.cargar()
        self.entorno = EntornoHotel(ESCENARIOS["E03"], 11)
        self.candado = threading.Lock()
        self._presupuesto_lock = threading.Lock()
        self._traza_lock = threading.Lock()
        self._dia_utc = datetime.now(timezone.utc).date()
        self._tokens_dia = 0
        self._trazas: list[dict] = []
        self._trazas_demo = self._cargar_trazas_demo()
        self._indice_traza_demo = 0

        demo_default = Path(tempfile.gettempdir()) / "reviewpulse-demo.sqlite3"
        self.demo_path = Path(os.environ.get("REVIEWPULSE_DB_PATH", str(demo_default)))
        self.demo_path.parent.mkdir(parents=True, exist_ok=True)
        self.directorio_salida = self.demo_path.parent / f"{self.demo_path.stem}_salidas"
        self.directorio_salida.mkdir(parents=True, exist_ok=True)
        self.reportes = GeneradorReporte(self.directorio_salida)
        self.notificador = Notificador(
            self.directorio_salida, "gerente@hotelpiloto.co"
        )
        self.cfg = {**CONFIG_DEFECTO}
        self.repo_demo = RepositorioHistorico(self.demo_path)
        self._inicializar_demo()

    @staticmethod
    def _cargar_trazas_demo() -> list[dict]:
        raiz = Path(__file__).resolve().parents[3]
        archivos = sorted((raiz / "data" / "trazas_demo").glob("*.json"))
        if len(archivos) != 3:
            raise RuntimeError("Se requieren exactamente tres trazas en data/trazas_demo.")

        trazas = []
        for archivo in archivos:
            traza = json.loads(archivo.read_text(encoding="utf-8"))
            if (
                not isinstance(traza, dict)
                or not isinstance(traza.get("id"), str)
                or not isinstance(traza.get("eventos"), list)
                or not traza["eventos"]
                or any(not isinstance(evento, dict) for evento in traza["eventos"])
            ):
                raise ValueError(f"Formato inválido en la traza demo {archivo.name}.")
            trazas.append(traza)
        return trazas

    def _inicializar_demo(self) -> None:
        existe = self.repo_demo.con.execute(
            "SELECT 1 FROM semanas LIMIT 1"
        ).fetchone()
        if existe:
            ids = {
                fila["id"]
                for fila in self.repo_demo.con.execute("SELECT id FROM resenas")
            }
            if ids != {"DEMO-001", "DEMO-002", "DEMO-003"}:
                return
            self.repo_demo.cerrar()
            for ruta in (
                self.demo_path,
                Path(f"{self.demo_path}-wal"),
                Path(f"{self.demo_path}-shm"),
            ):
                ruta.unlink(missing_ok=True)
            self.repo_demo = RepositorioHistorico(self.demo_path)

        self.repo_demo.cerrar()
        with tempfile.TemporaryDirectory(prefix="reviewpulse-e03-") as temporal:
            carpeta = Path(temporal) / "simulacion"
            ejecutar_simulacion(
                self.entorno,
                carpeta,
                cfg=self.cfg,
                modelo=self.modelo,
            )
            shutil.copy2(carpeta / "memoria.db", self.demo_path)
            reportes_origen = carpeta / "reportes"
            reportes_destino = self.directorio_salida / "reportes"
            shutil.copytree(reportes_origen, reportes_destino, dirs_exist_ok=True)

            with closing(sqlite3.connect(self.demo_path)) as conexion, conexion:
                filas = conexion.execute(
                    "SELECT semana, ruta FROM reportes"
                ).fetchall()
                for semana, ruta in filas:
                    destino = reportes_destino / Path(ruta).name
                    conexion.execute(
                        "UPDATE reportes SET ruta = ? WHERE semana = ?",
                        (str(destino), semana),
                    )

        self.repo_demo = RepositorioHistorico(self.demo_path)

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
            self.modelo,
            self.entorno,
            self.notificador,
            self.reportes,
            dict(self.cfg),
            datetime.now(timezone.utc),
            Sesion(),
        )

    def siguiente_traza_demo(self) -> dict:
        with self._traza_lock:
            traza = self._trazas_demo[self._indice_traza_demo]
            self._indice_traza_demo = (
                self._indice_traza_demo + 1
            ) % len(self._trazas_demo)
            return json.loads(json.dumps(traza, ensure_ascii=False))

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
