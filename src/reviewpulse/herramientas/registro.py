"""Registro tipado de herramientas y dispatcher defensivo, independiente del LLM."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from pydantic import BaseModel, ValidationError


@dataclass
class Sesion:
    comparaciones_positivas: set[tuple[int, str]] = field(default_factory=set)
    incompleto: bool = False
    # Autorización puntual: solo el manejador del cierre escribe aquí.
    semana_en_cierre: int | None = None
    # Únicamente el código de comparar_semana escribe en este mapa; no el LLM.
    comparaciones: dict[tuple[int, str], dict] = field(default_factory=dict, repr=False)


@dataclass
class Contexto:
    repo: Any
    modelo: Any
    entorno: Any
    notificador: Any
    reportes: Any
    cfg: dict
    ahora: datetime
    sesion: Sesion


@dataclass(frozen=True)
class _Entrada:
    descripcion: str
    esquema: type[BaseModel]
    funcion: Callable


_REGISTRO: dict[str, _Entrada] = {}
_CARGADO = False


class ErrorHerramienta(Exception):
    """Error esperado, con código público y detalle no sensible."""

    def __init__(self, codigo: str, detalle: str):
        super().__init__(detalle)
        self.codigo = codigo
        self.detalle = detalle


def herramienta(nombre: str, descripcion: str, esquema: type[BaseModel]):
    """Registra una función que recibe (argumentos_validados, contexto)."""
    if not issubclass(esquema, BaseModel):
        raise TypeError("La herramienta necesita un esquema Pydantic.")

    def decorar(funcion: Callable):
        if nombre in _REGISTRO:
            raise ValueError(f"Herramienta duplicada: {nombre}")
        _REGISTRO[nombre] = _Entrada(descripcion, esquema, funcion)
        return funcion

    return decorar


def _cargar_herramientas() -> None:
    global _CARGADO
    if _CARGADO:
        return
    # Importaciones con efectos deliberados: cada módulo registra sus funciones.
    from . import alertas, analisis, plataformas, reportes, resenas  # noqa: F401
    _CARGADO = True


def catalogo_openai() -> list[dict]:
    _cargar_herramientas()
    return [
        {
            "type": "function",
            "function": {
                "name": nombre,
                "description": entrada.descripcion,
                "parameters": entrada.esquema.model_json_schema(),
            },
        }
        for nombre, entrada in _REGISTRO.items()
    ]


def ejecutar(nombre: str, argumentos_crudos: str, ctx: Contexto) -> dict:
    """Convierte fallos de herramienta en datos, sin filtrar excepciones privadas."""
    _cargar_herramientas()
    entrada = _REGISTRO.get(nombre)
    if entrada is None:
        return {"ok": False, "error": "herramienta_desconocida", "detalle": "Herramienta no registrada."}
    if not isinstance(argumentos_crudos, str):
        return {"ok": False, "error": "argumentos_invalidos", "detalle": "Los argumentos deben ser JSON."}
    try:
        crudos = json.loads(argumentos_crudos)
        if not isinstance(crudos, dict):
            raise ValueError("Se esperaba un objeto JSON.")
        argumentos = entrada.esquema.model_validate(crudos)
    except (ValueError, TypeError, ValidationError):
        return {"ok": False, "error": "argumentos_invalidos", "detalle": "JSON o campos no válidos."}
    try:
        resultado = entrada.funcion(argumentos, ctx)
    except ErrorHerramienta as exc:
        return {"ok": False, "error": exc.codigo, "detalle": exc.detalle}
    except Exception:
        # No se devuelven trazas, rutas de archivo, mensajes SQL ni secretos.
        return {"ok": False, "error": "error_interno", "detalle": "La operación no pudo completarse."}
    return {"ok": True, "datos": resultado}
