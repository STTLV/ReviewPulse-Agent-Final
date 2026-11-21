"""Memoria de corto plazo para conversaciones del agente."""
from __future__ import annotations

from copy import deepcopy


class MemoriaSesion:
    def __init__(self, sistema: str):
        if not isinstance(sistema, str) or not sistema.strip():
            raise ValueError("Se requiere un prompt de sistema no vacío.")
        self.mensajes: list[dict] = [{"role": "system", "content": sistema}]

    def agregar(self, mensaje: dict) -> None:
        if not isinstance(mensaje, dict) or mensaje.get("role") not in {
            "system", "user", "assistant", "tool",
        }:
            raise ValueError("Mensaje de conversación no válido.")
        self.mensajes.append(deepcopy(mensaje))

    def contexto(self, tarea: str) -> list[dict]:
        """Retorna una copia de la conversación con la consulta nueva."""
        if not isinstance(tarea, str) or not tarea.strip():
            raise ValueError("La tarea no puede estar vacía.")
        return deepcopy(self.mensajes) + [{"role": "user", "content": tarea}]
