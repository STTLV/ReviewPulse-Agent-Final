"""Traza de decisiones JSONL, con redacción de credenciales y PII."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CLAVES_PRIVADAS = {"key", "api_key", "llm_api_key", "secret", "secreto", "clave", "password",
                   "contraseña", "authorization", "token", "access_token", "credential", "credencial"}
_PATRON_CREDENCIAL = re.compile(r"(?i)(?:sk-[A-Za-z0-9_-]{8,}|bearer\s+[A-Za-z0-9_.-]{8,})")


def _seguro(objeto: Any, profundidad: int = 0) -> Any:
    if profundidad >= 8:
        return "[contenido omitido]"
    if isinstance(objeto, dict):
        return {
            str(clave): ("[oculto]" if str(clave).lower() in _CLAVES_PRIVADAS else _seguro(valor, profundidad + 1))
            for clave, valor in objeto.items()
        }
    if isinstance(objeto, (tuple, list, set)):
        return [_seguro(valor, profundidad + 1) for valor in list(objeto)[:20]]
    if isinstance(objeto, (int, float, bool)) or objeto is None:
        return objeto
    texto = _PATRON_CREDENCIAL.sub("[oculto]", str(objeto))
    return texto[:2000] + ("…" if len(texto) > 2000 else "")


class Traza:
    def __init__(self, ruta: Path | None = None):
        self.ruta = Path(ruta) if ruta is not None else None
        self.eventos: list[dict] = []
        if self.ruta is not None:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)

    def evento(self, fase: str, evento: str, **datos) -> dict:
        registro = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "fase": str(fase),
            "evento": str(evento),
            **_seguro(datos),
        }
        self.eventos.append(registro)
        if self.ruta is not None:
            with self.ruta.open("a", encoding="utf-8") as archivo:
                archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
        return registro
