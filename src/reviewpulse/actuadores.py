"""Actuadores: lo que el agente cambia en su entorno.

- Notificador: envía la alerta al gerente. En el piloto escribe en una bandeja
  de salida (JSONL) que simula el correo; si se configura SMTP, envía correo real.
- GeneradorReporte: arma el resumen semanal por tema en Markdown y JSON.
- Las etiquetas y el registro histórico se escriben a través del repositorio.
"""
from __future__ import annotations

import json
import smtplib
from email.message import EmailMessage
from pathlib import Path

from .corpus import TEMAS

NOMBRE_TEMA = {"limpieza": "Limpieza", "servicio": "Servicio", "ubicacion": "Ubicación", "precio": "Precio"}


class Notificador:
    def __init__(self, carpeta: Path, destinatario: str, smtp: dict | None = None):
        self.bandeja = carpeta / "bandeja_salida.jsonl"
        self.destinatario, self.smtp = destinatario, smtp

    def redactar(self, a: dict) -> str:
        tema = NOMBRE_TEMA[a["tema"]]
        tardia = " (detectada con reseñas que llegaron tarde)" if a["tipo"] == "tardia" else ""
        return (f"Alerta ReviewPulse, semana {a['semana_texto']}{tardia}: las reseñas negativas sobre "
                f"{tema.lower()} subieron a {a['proporcion']:.0%} ({a['negativas']:.0f} de {a['total']:.0f}), "
                f"frente a un promedio de {a['promedio']:.0%} en las últimas {a['k']} semanas. "
                f"La probabilidad de ver un aumento así por simple azar es {a['p_valor']:.4f}. "
                f"Ejemplos: " + " | ".join(f"“{e}”" for e in a["ejemplos"][:2]))

    def enviar(self, alerta: dict, ts: str) -> dict:
        mensaje = self.redactar(alerta)
        registro = {"enviado_en": ts, "para": self.destinatario, "asunto": f"[ReviewPulse] Alerta de "
                    f"{NOMBRE_TEMA[alerta['tema']]}", "mensaje": mensaje}
        with self.bandeja.open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        if self.smtp:  # opcional, no se usa en las pruebas
            em = EmailMessage()
            em["Subject"], em["From"], em["To"] = registro["asunto"], self.smtp["usuario"], self.destinatario
            em.set_content(mensaje)
            with smtplib.SMTP_SSL(self.smtp["host"], self.smtp.get("puerto", 465)) as s:
                s.login(self.smtp["usuario"], self.smtp["clave"])
                s.send_message(em)
        return registro


class GeneradorReporte:
    def __init__(self, carpeta: Path):
        self.carpeta = carpeta / "reportes"
        self.carpeta.mkdir(parents=True, exist_ok=True)

    def generar(self, semana: int, semana_texto: str, conteos: dict, comparacion: dict, alertas: list,
                incompleto: bool, revision_manual: int, ts: str) -> Path:
        filas = []
        for t in TEMAS:
            c = conteos[t]
            n = sum(c.values())
            comp = comparacion.get(t, {})
            filas.append(f"| {NOMBRE_TEMA[t]} | {n:g} | {c['positiva']:g} | {c['neutra']:g} | "
                         f"{c['negativa']:g} | {comp.get('proporcion', 0):.0%} | "
                         f"{comp.get('promedio', 0):.0%} | {'⚠️ Sí' if t in [a['tema'] for a in alertas] else 'No'} |")
        total = sum(sum(c.values()) for c in conteos.values())
        lineas = [
            f"# Resumen semanal ReviewPulse — semana {semana_texto}",
            f"Generado: {ts} · Reseñas clasificadas: {total:.1f} · Para revisión manual: {revision_manual}",
            "Conteos ponderados: una reseña con confianza baja (revisión manual) cuenta 0,5.",
            "",
            "> ⚠️ Datos incompletos: una o más plataformas no respondieron al cierre." if incompleto else "",
            "| Tema | Reseñas | Positivas | Neutras | Negativas | % negativas | Promedio histórico | Alerta |",
            "|---|---|---|---|---|---|---|---|",
            *filas,
            "",
            "## Alertas de la semana",
            *([f"- {a['mensaje']}" for a in alertas] or ["- Sin alertas: la variación está dentro de lo normal."]),
        ]
        ruta = self.carpeta / f"semana_{semana:02d}.md"
        ruta.write_text("\n".join(l for l in lineas if l is not None), encoding="utf-8")
        (self.carpeta / f"semana_{semana:02d}.json").write_text(json.dumps(
            {"semana": semana, "generado_en": ts, "conteos": conteos, "comparacion": comparacion,
             "alertas": alertas, "datos_incompletos": incompleto}, ensure_ascii=False, indent=2), encoding="utf-8")
        return ruta
