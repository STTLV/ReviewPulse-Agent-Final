"""Limpieza y validación de las percepciones antes de que lleguen al modelo."""
from __future__ import annotations

import html
import re
import unicodedata

_STOP = {
    "es": {"el", "la", "los", "las", "de", "que", "y", "en", "un", "una", "muy", "por", "con", "para",
           "nos", "no", "es", "lo", "del", "al", "estaba", "fue", "todo", "pero", "hotel", "habitacion", "se"},
    "en": {"the", "and", "was", "very", "of", "to", "we", "is", "it", "room", "staff", "at", "for", "with"},
    "pt": {"o", "e", "muito", "atendimento", "quarto", "perto", "da", "foi", "estava", "bem", "com"},
    "fr": {"le", "et", "très", "était", "chambre", "personnel", "les", "du", "aimable"},
}


def limpiar(texto) -> str:
    """Quita HTML, entidades, espacios repetidos y valores nulos."""
    if texto is None:
        return ""
    texto = html.unescape(str(texto))
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = texto.replace("\xa0", " ")
    if texto.strip().lower() in {"null", "none", "nan"}:
        return ""
    return re.sub(r"\s+", " ", texto).strip()


def normalizar(texto: str) -> str:
    """Forma canónica para el modelo: minúsculas, sin tildes, letras repetidas reducidas."""
    texto = limpiar(texto).lower()
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return re.sub(r"(.)\1{2,}", r"\1\1", texto)


def tiene_contenido(texto: str) -> bool:
    """Al menos tres palabras con letras."""
    return len(re.findall(r"[a-záéíóúñü]{2,}", texto.lower())) >= 3


def detectar_idioma(texto: str) -> str:
    palabras = re.findall(r"[a-záéíóúñüç]+", normalizar(texto)) or [""]
    puntajes = {k: sum(p in v for p in palabras) for k, v in _STOP.items()}
    mejor = max(puntajes, key=puntajes.get)
    return mejor if puntajes[mejor] > 0 else "desconocido"


def validar(resena: dict) -> tuple[bool, str, str]:
    """Devuelve (es_valida, texto_limpio, motivo_descartada)."""
    texto = limpiar(resena.get("texto"))
    if not resena.get("fecha"):
        return False, texto, "sin_fecha"
    if not tiene_contenido(texto):
        return False, texto, "texto_vacio_o_ruido"
    idioma = detectar_idioma(texto)
    if idioma != "es":
        return False, texto, f"idioma_{idioma}"
    return True, texto, ""
