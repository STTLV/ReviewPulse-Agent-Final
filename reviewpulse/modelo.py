"""Herramienta externa al agente: modelo de clasificación de sentimiento y tema.

Implementación: TF-IDF (palabras 1-2 y caracteres 2-5) + regresión logística
multinomial, uno para polaridad y otro para tema. Devuelve probabilidades, de
modo que el agente puede razonar con la confianza de cada predicción.

El diseño original proponía un modelo tipo BERT ajustado para español. En este
entorno de desarrollo no hay acceso a Hugging Face, por eso se usa un modelo
clásico de scikit-learn con la misma interfaz (`predecir`). La clase
`ClasificadorBERT` deja el punto de reemplazo listo (ver sección 9.6).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from .corpus import construir_corpus
from .lexico import RasgosLexico
from .preprocesamiento import normalizar

RUTA_MODELO = Path(__file__).resolve().parent.parent / "datos" / "modelo.joblib"


@dataclass
class Prediccion:
    polaridad: str
    conf_polaridad: float
    tema: str
    conf_tema: float
    prob_polaridad: dict
    prob_tema: dict

    @property
    def confianza(self) -> float:
        return min(self.conf_polaridad, self.conf_tema)


def _pipeline() -> Pipeline:
    vector = FeatureUnion([
        ("palabras", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ("caracteres", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)),
        ("lexico", RasgosLexico()),
    ], transformer_weights={"palabras": 1.0, "caracteres": 1.0, "lexico": 2.0})
    return Pipeline([("tfidf", vector), ("clf", LogisticRegression(C=4.0, max_iter=2000))])


class ClasificadorSentimiento:
    def __init__(self):
        self.pol = _pipeline()
        self.tema = _pipeline()
        self.version = "tfidf+lexico-logreg-2.0"

    def entrenar(self, corpus: list[dict]) -> "ClasificadorSentimiento":
        textos = [normalizar(r["texto"]) for r in corpus]
        self.pol.fit(textos, [r["polaridad"] for r in corpus])
        self.tema.fit(textos, [r["tema"] for r in corpus])
        return self

    def predecir(self, textos: list[str]) -> list[Prediccion]:
        if not textos:
            return []
        norm = [normalizar(t) for t in textos]
        pp, pt = self.pol.predict_proba(norm), self.tema.predict_proba(norm)
        salida = []
        for fila_p, fila_t in zip(pp, pt):
            dp = dict(zip(self.pol.classes_, map(float, fila_p)))
            dt = dict(zip(self.tema.classes_, map(float, fila_t)))
            p, t = max(dp, key=dp.get), max(dt, key=dt.get)
            salida.append(Prediccion(p, dp[p], t, dt[t], dp, dt))
        return salida

    def guardar(self, ruta: Path = RUTA_MODELO):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, ruta)

    @staticmethod
    def cargar(ruta: Path = RUTA_MODELO) -> "ClasificadorSentimiento":
        if not ruta.exists():
            return entrenar_modelo_base()
        try:
            return joblib.load(ruta)
        except Exception as exc:  # guardado con una versión incompatible de scikit-learn
            print(f"Aviso: no se pudo cargar {ruta.name} ({exc}); se reentrena el modelo.")
            return entrenar_modelo_base()


def entrenar_modelo_base(semilla: int = 7, n: int = 4000, guardar: bool = True) -> ClasificadorSentimiento:
    """Entrena antes del despliegue (el agente no reentrena mientras opera)."""
    corpus = construir_corpus(n, semilla, conjunto="entrenamiento", prob_ironia=0.10)
    modelo = ClasificadorSentimiento().entrenar(corpus)
    if guardar:
        modelo.guardar()
    return modelo


class ClasificadorBERT:  # pragma: no cover - punto de extensión documentado
    """Reemplazo previsto: pysentimiento/robertuito o un BETO ajustado (IberLEF 2021).

    Para activarlo: `pip install transformers torch`, cargar el modelo y devolver
    objetos `Prediccion` con la misma forma. El resto del agente no cambia.
    """

    def __init__(self, nombre_modelo: str = "pysentimiento/robertuito-sentiment-analysis"):
        raise NotImplementedError("Requiere acceso a Hugging Face; ver README, sección 'Modelo BERT'.")
