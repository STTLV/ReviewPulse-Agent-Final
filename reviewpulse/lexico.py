"""Léxico de sentimiento y de temas para español de reseñas de hospedaje.

Se usa como característica adicional del modelo (no como regla final): el
clasificador aprende cuánto pesar cada señal. Incluye manejo simple de negación
("no vale la pena", "nunca llegó") invirtiendo la polaridad de la palabra que
sigue a un negador dentro de una ventana de tres palabras.
"""
from __future__ import annotations

import re

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

POSITIVAS = (
    "excelent impecabl limpi relimpi pulcr brill perfect espectacular recomend maravill encant buen buenisim "
    "bonit rapid agil atent querid calid amabl amor sonris sorpres cordial servicial agradabl comod econom barat "
    "ganga ofert promocion justo accesibl inmejorabl mejor segur tranquil fresc higien orden organiz gust feliz "
    "genial increibl super complet ampli dispuest pendient resolv ayud solucion vale cumplidor estrategic "
    "hermos lind delici fabulos"
).split()
NEGATIVAS = (
    "suci mal malo mala pesim horribl terribl asco grosero demor eternid nunca nadie cucarach moho hongo manch "
    "ruid insegur peligros lejos lejisim car carisim costos estaf robo abus ocult decepcion desagrad desprec feo "
    "fea basur huec ignor perdi sobrevalor exager peor problem percud pegajos turbi oscur mied caos estorb "
    "equivoc seco seca grit queja reclam incomod olor humed polvo pocilg desastr lamentabl fatal "
    "jamas obra"
).split()
NEUTRAS = (
    "normal normalit promedi aceptabl regular correct cumpl estandar esperad acord comun basic neutral "
    "presentabl intermedi sin_mas ni_mas ni_bien ni_caro nada_especial nada_del parecid cualquier"
).split()
NEGADORES = {"no", "ni", "nunca", "sin", "tampoco", "jamas", "nadie", "nada", "cero"}
EXCEPCIONES_NEG = ("mejorar", "deberian", "deben")

TEMAS_LEX = {
    "limpieza": "limpi suci aseo ase polvo toall saban bano ducha moho hongo cucarach olor manch piscin pelo "
                "higien desinfect cortin tapet orden trape basur colchon almohad desagu camarer espejo",
    "servicio": "personal recepcion atencion atend amabl meser boton trato servici check reserv emplead ayud "
                "gerent senor don muchach conserj recepcionist llav malet espera esperar pedid respond trat",
    "ubicacion": "ubicacion ubicad zona sector cerc lejos play centr call ruid taxi barri malecon cuadr obra "
                 "construccion afuer estacion vista alrededor caminand camin transport aeropuert discotec",
    "precio": "precio car barat cobr cobro tarif pag valor plata peso ofert promocion econom costos estaf cuest "
              "parqueader factur cargo ganga presupuest minibar mitad devolv",
}
TEMAS_LEX = {k: v.split() for k, v in TEMAS_LEX.items()}

_FRASES_NEUTRAS = [("sin", "mas"), ("ni", "mas"), ("ni", "bien"), ("ni", "caro"), ("nada", "especial"),
                   ("nada", "del")]


def _tokens(texto: str) -> list[str]:
    return re.findall(r"[a-zñ]+", texto)


def _empieza(tok: str, raices: list[str]) -> bool:
    return any(tok.startswith(r) for r in raices if len(r) >= 3) or tok in raices


def rasgos(texto: str) -> list[float]:
    toks = _tokens(texto)
    pos = neg = neu = 0.0
    for i, t in enumerate(toks):
        negado = any(x in NEGADORES for x in toks[max(0, i - 3):i])
        if t.startswith(EXCEPCIONES_NEG):
            neg += 1
        elif _empieza(t, POSITIVAS):
            if negado:
                neg += 1
            else:
                pos += 1
        elif t in NEGADORES:
            continue  # el negador modifica la palabra siguiente, no cuenta por sí mismo
        elif _empieza(t, NEGATIVAS):
            if negado:
                pos += 1  # "cero polvo", "ni un pelo", "sin manchas"
            else:
                neg += 1
        if _empieza(t, [n for n in NEUTRAS if "_" not in n]):
            neu += 1
    for a, b in _FRASES_NEUTRAS:
        neu += sum(1 for i in range(len(toks) - 1) if toks[i] == a and toks[i + 1].startswith(b)) * 2
    total = max(len(toks), 1)
    temas = [sum(_empieza(t, raices) for t in toks) for raices in TEMAS_LEX.values()]
    return [pos, neg, neu, pos - neg, (pos - neg) / total, float(pos == neg == 0), *temas]


class RasgosLexico(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return np.array([rasgos(x) for x in X], dtype=float) / 3.0
