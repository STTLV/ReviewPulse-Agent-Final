"""ReviewPulse-Agent: agente basado en modelos y orientado a metas.

Ciclo de cada paso (cada 6 horas de tiempo simulado):

    percepcion = agente.percibir(ahora)   # SENSORES: conectores + reloj + historial + configuración
    plan       = agente.decidir(percepcion) # DECISIÓN: estado interno -> meta -> plan (BFS) -> reglas
    agente.actuar(plan, percepcion)       # ACTUADORES: etiquetas, reporte, alerta, registro histórico

El estado interno (modelo del mundo) vive en `MemoriaTrabajo` (semanas abiertas)
y en `RepositorioHistorico` (semanas cerradas, alertas y reportes).
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .actuadores import GeneradorReporte, Notificador
from .corpus import TEMAS
from .entorno import PLATAFORMAS, INICIO, EntornoHotel, PlataformaNoDisponible, inicio_semana, semana_de
from .memoria import MemoriaTrabajo, RepositorioHistorico, conteo_vacio
from .modelo import ClasificadorSentimiento
from .planificador import METAS, planificar
from .preprocesamiento import validar

CONFIG_DEFECTO = {
    "umbral_confianza": 0.55,      # por debajo, la reseña va a revisión manual y pesa 0.5
    "alfa": 0.08,                  # significancia global; se divide entre los 4 temas (Bonferroni)
    "delta_minimo": 0.25,          # aumento mínimo de la proporción negativa frente al promedio
    "min_negativas": 6,            # mínimo de reseñas negativas del tema para alertar
    "z_minimo": 0.0,               # z sobre el historial; la calibración lo dejó inactivo (redundante)
    "semanas_historial": 6,        # ventana de comparación
    "min_semanas_historial": 3,    # sin esto no se alerta (arranque en frío)
    "margen_espera_h": 12,         # espera reseñas tardías antes de cerrar la semana
    "plazo_reporte_h": 24,         # meta: reporte dentro de 24 h tras el cierre
    "intervalo_h": 6,              # periodicidad del ciclo del agente
    "destinatario": "gerente@hotelpiloto.co",
}


def texto_semana(s: int) -> str:
    ini = inicio_semana(s)
    return f"{s:02d} ({ini:%d/%m}–{ini + timedelta(days=6):%d/%m/%Y})"


def cola_binomial(k: float, n: float, p: float) -> float:
    """P(X >= k) con X ~ Binomial(n, p). Acepta conteos ponderados (se redondean)."""
    k, n = int(math.ceil(k - 1e-9)), int(round(n))
    if n <= 0 or k <= 0:
        return 1.0
    p = min(max(p, 1e-6), 1 - 1e-6)
    return float(sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1)))


class Bitacora:
    """Log de ejecución: cada percepción, decisión y acción con marca de tiempo."""

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.f = ruta.open("w", encoding="utf-8")
        self.eventos: list[dict] = []

    def __call__(self, ahora: datetime, fase: str, evento: str, **datos):
        e = {"ts_real": datetime.now().isoformat(timespec="milliseconds"), "ts_simulado": ahora.isoformat(),
             "fase": fase, "evento": evento, **datos}
        self.eventos.append(e)
        self.f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")

    def cerrar(self):
        # Puede llamarse desde una ruta de salida normal o desde un finally.
        if not self.f.closed:
            self.f.close()


@dataclass
class Percepcion:
    ahora: datetime
    lote: list[dict]
    disponibilidad: dict
    semanas_cerradas_pendientes: list[int]
    horas_desde_cierre: dict
    config: dict


@dataclass
class Plan:
    meta: str
    acciones: list[str]
    hechos: list[str]
    semana_objetivo: int | None = None
    motivo: str = ""
    decisiones: dict = field(default_factory=dict)


class ReviewPulseAgent:
    def __init__(self, entorno: EntornoHotel, carpeta: Path, config: dict | None = None,
                 modelo: ClasificadorSentimiento | None = None):
        self.entorno = entorno
        self.cfg = {**CONFIG_DEFECTO, **(config or {})}
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.modelo = modelo or ClasificadorSentimiento.cargar()
        self.memoria = MemoriaTrabajo()
        self.repo = RepositorioHistorico(self.carpeta / "memoria.db")
        self.notificador = Notificador(self.carpeta, self.cfg["destinatario"])
        self.reportes = GeneradorReporte(self.carpeta)
        self.log = Bitacora(self.carpeta / "log_ejecucion.jsonl")
        self.cursor = {p: INICIO - timedelta(days=1) for p in PLATAFORMAS}
        self.semanas_reportadas: set[int] = set()
        self.tardias_por_semana: dict[int, int] = {}
        self._lote_trabajo: list[dict] = []
        self._clasificadas: list[dict] = []

    # ------------------------------------------------------------------ PERCEPCIÓN
    def percibir(self, ahora: datetime) -> Percepcion:
        lote, disp = [], {}
        for p in PLATAFORMAS:  # sensor 1 y 2: texto + metadatos de cada plataforma
            try:
                nuevas = self.entorno.consultar(p, self.cursor[p], ahora)
                self.cursor[p] = ahora
                disp[p] = True
                lote.extend(nuevas)
            except PlataformaNoDisponible as e:
                disp[p] = False
                self.log(ahora, "PERCEPCION", "plataforma_no_disponible", plataforma=p, error=str(e))
        semana_actual = semana_de(ahora)
        pendientes = [s for s in range(semana_actual) if s not in self.semanas_reportadas]  # sensor 3: historial
        horas = {s: (ahora - inicio_semana(s + 1)).total_seconds() / 3600 for s in pendientes}
        per = Percepcion(ahora, lote, disp, pendientes, horas, self.cfg)  # sensor 4: configuración
        self.log(ahora, "PERCEPCION", "lectura_sensores", nuevas=len(lote), disponibilidad=disp,
                 semanas_pendientes=pendientes, ids=[r["id"] for r in lote])
        return per

    # ------------------------------------------------------------------ DECISIÓN
    def _hechos(self, per: Percepcion, semana: int | None) -> frozenset:
        h = set()
        if per.lote:
            h.add("lote_nuevo")
        else:
            h.add("conteos_al_dia")
        if any(r["fecha"] and semana_de(datetime.fromisoformat(r["fecha"])) in self.semanas_reportadas
               for r in per.lote):
            h.add("hay_tardias")
        if semana is not None:
            h.add("semana_cerrada")
            horas = per.horas_desde_cierre[semana]
            todas = all(per.disponibilidad.values())
            ultimo_ciclo = horas + self.cfg["intervalo_h"] > self.cfg["plazo_reporte_h"]
            if (horas >= self.cfg["margen_espera_h"] and todas) or ultimo_ciclo:
                h.add("puede_cerrar")
        return frozenset(h)

    def decidir(self, per: Percepcion) -> Plan:
        semana = per.semanas_cerradas_pendientes[0] if per.semanas_cerradas_pendientes else None
        hechos = self._hechos(per, semana)
        metas = ["mantener_conteos_al_dia"]
        if "hay_tardias" in hechos:
            metas.append("revisar_semanas_cerradas")
        if semana is not None:
            metas.append("entregar_resumen_semanal")
        meta = frozenset().union(*(METAS[m] for m in metas))
        acciones = planificar(hechos, meta)
        motivo = "plan completo"
        if acciones is None and semana is not None:  # la meta de reporte aún no es alcanzable
            metas.remove("entregar_resumen_semanal")
            acciones = planificar(hechos, frozenset().union(*(METAS[m] for m in metas))) or []
            horas = per.horas_desde_cierre[semana]
            motivo = ("esperar reintento: plataforma caída y aún hay plazo" if not all(per.disponibilidad.values())
                      else f"esperar margen de reseñas tardías ({horas:.0f} h de {self.cfg['margen_espera_h']} h)")
        plan = Plan("+".join(metas), acciones or [], sorted(hechos), semana, motivo)
        self.log(per.ahora, "DECISION", "plan", meta=plan.meta, acciones=plan.acciones, hechos=plan.hechos,
                 semana=semana, motivo=motivo)
        return plan

    def _evaluar_semana(self, semana: int, conteos: dict, ahora: datetime) -> tuple[dict, list]:
        """Razonamiento: compara la semana contra el historial con una prueba binomial por tema."""
        hist = self.repo.historial(semana, self.cfg["semanas_historial"])
        comp, candidatas = {}, []
        for t in TEMAS:
            c = conteos[t]
            n, neg = sum(c.values()), c["negativa"]
            prop = neg / n if n else 0.0
            props = [h["conteos"][t]["negativa"] / sum(h["conteos"][t].values())
                     for h in hist if sum(h["conteos"][t].values()) > 0]
            prom = sum(props) / len(props) if props else 0.0
            de = (sum((x - prom) ** 2 for x in props) / (len(props) - 1)) ** 0.5 if len(props) > 1 else 0.0
            z = (prop - prom) / max(de, 0.05)
            # promedio suavizado para evitar p=0 con historiales pequeños
            base = (sum(h["conteos"][t]["negativa"] for h in hist) + 1) / (
                sum(sum(h["conteos"][t].values()) for h in hist) + 4)
            pval = cola_binomial(neg, n, base) if props else 1.0
            razon = []
            if len(hist) < self.cfg["min_semanas_historial"]:
                razon.append("historial_insuficiente")
            if pval >= self.cfg["alfa"] / len(TEMAS):
                razon.append("p_valor_alto")
            if prop - prom < self.cfg["delta_minimo"]:
                razon.append("aumento_menor_al_delta")
            if neg < self.cfg["min_negativas"]:
                razon.append("pocas_negativas")
            if z < self.cfg["z_minimo"]:
                razon.append("z_bajo")
            comp[t] = {"total": n, "negativas": neg, "proporcion": prop, "promedio": prom, "base": base,
                       "desviacion": de, "z": z, "p_valor": pval, "semanas_historial": len(hist), "alerta": not razon,
                       "motivos_no_alerta": razon}
            if not razon:
                candidatas.append(t)
        return comp, candidatas

    # ------------------------------------------------------------------ ACCIÓN
    def actuar(self, plan: Plan, per: Percepcion):
        ahora, ts = per.ahora, per.ahora.isoformat()
        for accion in plan.acciones:
            getattr(self, f"_a_{accion}")(plan, per)
            self.log(ahora, "ACCION", accion, semana=plan.semana_objetivo)
        if plan.semana_objetivo is not None and "registrar_historial" not in plan.acciones:
            self.log(ahora, "ACCION", "esperar", semana=plan.semana_objetivo, motivo=plan.motivo)

    def _a_limpiar_lote(self, plan, per):
        self._lote_trabajo = []
        for r in per.lote:
            ok, texto, motivo = validar(r)
            if ok:
                self._lote_trabajo.append({**r, "texto": texto})
            else:
                self.repo.guardar_descartada(r["id"], motivo, per.ahora.isoformat())
                self.log(per.ahora, "DECISION", "descartar_resena", id=r["id"], motivo=motivo)

    def _a_clasificar_lote(self, plan, per):
        preds = self.modelo.predecir([r["texto"] for r in self._lote_trabajo])
        self._clasificadas = []
        for r, p in zip(self._lote_trabajo, preds):
            revision = p.confianza < self.cfg["umbral_confianza"]
            fila = {**r, "semana": semana_de(datetime.fromisoformat(r["fecha"])), "polaridad": p.polaridad,
                    "tema": p.tema, "confianza": round(p.confianza, 4), "revision_manual": revision,
                    "procesada_en": per.ahora.isoformat()}
            self.repo.guardar_resena(fila)  # actuador 1: etiqueta en la base de datos
            self._clasificadas.append(fila)

    def _a_actualizar_conteos(self, plan, per):
        for r in self._clasificadas:
            peso = 0.5 if r["revision_manual"] else 1.0
            if r["semana"] in self.semanas_reportadas:  # reseña tardía de semana ya cerrada
                self.repo.ajustar_semana_tardia(r["semana"], r["tema"], r["polaridad"], peso)
                self.tardias_por_semana[r["semana"]] = self.tardias_por_semana.get(r["semana"], 0) + 1
            else:
                self.memoria.sumar(r["semana"], r["tema"], r["polaridad"], peso)
                if r["revision_manual"]:
                    self.memoria.revision_manual[r["semana"]] += 1
        self.repo.con.commit()
        self._clasificadas = []

    def _a_comparar_historial(self, plan, per):
        s = plan.semana_objetivo
        self._conteos_cierre = self.memoria.sacar(s)
        self._comp, self._candidatas = self._evaluar_semana(s, self._conteos_cierre, per.ahora)
        self.log(per.ahora, "DECISION", "comparacion_historial", semana=s,
                 comparacion={t: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in c.items()}
                              for t, c in self._comp.items()})

    def _ejemplos(self, semana, tema):
        filas = self.repo.con.execute("SELECT texto FROM resenas WHERE semana=? AND tema=? AND polaridad='negativa'"
                                      " ORDER BY confianza DESC LIMIT 2", (semana, tema)).fetchall()
        return [f[0][:110] for f in filas]

    def _emitir_alerta(self, semana, tema, c, ahora, tipo):
        a = {"semana": semana, "semana_texto": texto_semana(semana), "tema": tema, "proporcion": c["proporcion"],
             "promedio": c["promedio"], "p_valor": c["p_valor"], "negativas": c["negativas"], "total": c["total"],
             "k": c["semanas_historial"], "ejemplos": self._ejemplos(semana, tema), "tipo": tipo}
        reg = self.notificador.enviar(a, ahora.isoformat())  # actuador 3: notificación
        a.update(enviada_en=ahora.isoformat(), mensaje=reg["mensaje"])
        self.repo.guardar_alerta(a)
        return a

    def _a_decidir_alerta(self, plan, per):
        s = plan.semana_objetivo
        self._alertas = [self._emitir_alerta(s, t, self._comp[t], per.ahora, "a_tiempo") for t in self._candidatas]
        self.log(per.ahora, "DECISION", "decision_alerta", semana=s, alertar=self._candidatas)

    def _a_generar_reporte(self, plan, per):
        s = plan.semana_objetivo
        self._incompleto = not all(per.disponibilidad.values())
        ruta = self.reportes.generar(s, texto_semana(s), self._conteos_cierre, self._comp, self._alertas,
                                     self._incompleto, self.memoria.revision_manual.get(s, 0),
                                     per.ahora.isoformat())  # actuador 2: resumen semanal
        self.repo.guardar_reporte(s, per.ahora.isoformat(), str(ruta), self._incompleto)

    def _a_registrar_historial(self, plan, per):
        s = plan.semana_objetivo
        self.repo.cerrar_semana(s, self._conteos_cierre, self._incompleto, per.ahora.isoformat(),
                                bool(self._alertas))  # actuador 4: registro histórico
        self.semanas_reportadas.add(s)

    def _a_reevaluar_semanas_tardias(self, plan, per):
        """Ambiente dinámico: si llegaron reseñas tardías, reevalúa la semana ya reportada."""
        ya = {(a["semana"], a["tema"]) for a in self.repo.alertas()}
        for s in sorted(self.tardias_por_semana):
            fila = self.repo.semana(s)
            if not fila:
                continue
            comp, cand = self._evaluar_semana(s, fila["conteos"], per.ahora)
            for t in cand:
                if (s, t) not in ya:
                    self._emitir_alerta(s, t, comp[t], per.ahora, "tardia")
                    self.repo.marcar_alerta_semana(s)
                    self.log(per.ahora, "DECISION", "alerta_tardia", semana=s, tema=t)
        self.tardias_por_semana = {}

    # ------------------------------------------------------------------ BUCLE
    def paso(self, ahora: datetime):
        per = self.percibir(ahora)
        plan = self.decidir(per)
        self.actuar(plan, per)
        # si quedan más semanas pendientes y el plan se completó, se atienden en el mismo instante
        while plan.semana_objetivo is not None and "registrar_historial" in plan.acciones:
            per = Percepcion(ahora, [], per.disponibilidad,
                             [s for s in per.semanas_cerradas_pendientes if s not in self.semanas_reportadas],
                             per.horas_desde_cierre, self.cfg)
            if not per.semanas_cerradas_pendientes:
                break
            plan = self.decidir(per)
            self.actuar(plan, per)

    def ejecutar(self, horas_extra: int = 48) -> dict:
        """Ejecuta el ciclo completo y libera siempre los recursos del agente.

        El resultado se materializa antes de cerrar SQLite. El bloque finally
        garantiza que tanto el log como la conexión a la base de datos se cierren
        también si ocurre una excepción durante la ejecución. Esto evita que
        Windows mantenga bloqueado memoria.db al salir de TemporaryDirectory.
        """
        t0 = time.perf_counter()
        try:
            fin = inicio_semana(self.entorno.escenario.semanas) + timedelta(hours=horas_extra)
            ahora = INICIO + timedelta(hours=self.cfg["intervalo_h"])
            while ahora <= fin:
                self.paso(ahora)
                ahora += timedelta(hours=self.cfg["intervalo_h"])
            self.log(ahora, "SISTEMA", "fin_ejecucion", segundos=round(time.perf_counter() - t0, 2))
            return {
                "alertas": self.repo.alertas(),
                "reportes": self.repo.reportes(),
                "resenas": self.repo.resenas(),
                "descartadas": self.repo.descartadas(),
            }
        finally:
            # El cierre de SQLite debe ejecutarse incluso si falla el cierre del log.
            try:
                self.log.cerrar()
            finally:
                self.repo.cerrar()
