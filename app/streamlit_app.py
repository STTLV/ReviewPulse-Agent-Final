"""Interfaz de ReviewPulse-Agent (opción A de evidencia: Streamlit Community Cloud).

Ejecutar en local:  streamlit run app/streamlit_app.py

Dos partes:
  · Panel del hotel (lo que vería el gerente): resumen, historial de reseñas, resumen por semana
    y una caja para probar una reseña.
  · Demostración técnica (para la evaluación): ejecutar un escenario del simulador, ver el log
    percepción → decisión → acción y los resultados de las pruebas.
"""
from __future__ import annotations

import html
import json
import re
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from reviewpulse.agente import ReviewPulseAgent, texto_semana  # noqa: E402
from reviewpulse.entorno import EntornoHotel  # noqa: E402
from reviewpulse.escenarios import ESCENARIOS  # noqa: E402
from reviewpulse.evaluacion import evaluar_corrida  # noqa: E402
from reviewpulse.modelo import ClasificadorSentimiento  # noqa: E402
from reviewpulse.preprocesamiento import validar  # noqa: E402

st.set_page_config(page_title="ReviewPulse · Hotel piloto", layout="wide")

# ------------------------------------------------------------------ identidad visual
# Tinta ciruela como ancla, crema como lienzo, rosado y amarillo pastel como color de marca,
# coral solo para lo que requiere atención. Titulares en Bricolage Grotesque, texto en Plus Jakarta Sans.
ESTILO = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
:root { --crema: #FBF6EE; --papel: #FFFDF9; --tinta: #2A2230; --tinta2: #75697B; --linea: #E8DCCF;
        --rosa: #F7CFD8; --rosa2: #FCE9ED; --amarillo: #FBE6A2; --amarillo2: #FDF3CE; --coral: #DB6B5E; }
.stApp, .stApp p, .stApp label, .stApp li, .stApp input, .stApp textarea, .stApp button, .stApp table, .stApp th, .stApp td,
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stCaptionContainer"] {
    font-family: 'Plus Jakarta Sans', -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif !important; }
.stApp { background: var(--crema); color: var(--tinta); }
.block-container { padding-top: 2.4rem; padding-bottom: 4rem; max-width: 1120px; }
#MainMenu, footer { visibility: hidden; }
.display, .titulo, .n, .grande, .tema, .rango { font-family: 'Bricolage Grotesque', 'Plus Jakarta Sans', sans-serif !important; }

/* ---------- barra lateral */
[data-testid="stSidebar"] { background: var(--tinta); border-right: none; }
[data-testid="stSidebarUserContent"] { padding-top: 1.4rem; }
.marca { display: flex; align-items: center; gap: 13px; padding: 2px 6px 26px; }
.marca svg { flex: none; display: block; }
.marca .m1 { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 600; font-size: 1.28rem; color: #FBF6EE; line-height: 1.1;
    letter-spacing: -0.01em; }
.marca .m1 b { color: var(--rosa); font-weight: 700; }
.marca .m2 { font-size: 0.66rem; color: #A99DB1; letter-spacing: 0.18em; text-transform: uppercase; margin-top: 3px; }
.grupo { font-size: 0.66rem; letter-spacing: 0.18em; text-transform: uppercase; color: #8E8196; padding: 0 14px 8px; }
[data-testid="stSidebar"] [role="radiogroup"] { gap: 2px; }
[data-testid="stSidebar"] [role="radiogroup"] label { width: 100%; padding: 10px 14px; border-radius: 12px; cursor: pointer; position: relative; }
[data-testid="stSidebar"] [role="radiogroup"] label p { color: #D8CEDF; font-size: 0.93rem; font-weight: 500; letter-spacing: 0; }
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: rgba(255, 255, 255, 0.07); }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) { background: var(--amarillo); }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p { color: var(--tinta); font-weight: 700; }
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child:not(:has([data-testid="stMarkdownContainer"])) { display: none; }
[data-testid="stSidebar"] [role="radiogroup"] label:nth-of-type(5) { margin-top: 34px; }
[data-testid="stSidebar"] [role="radiogroup"] label:nth-of-type(5)::before { content: "AGENTE"; position: absolute; top: -26px; left: 14px;
    font-size: 0.66rem; letter-spacing: 0.18em; color: #8E8196; }

/* ---------- encabezados */
.enc { margin: 0 0 2rem; padding-bottom: 1.3rem; border-bottom: 1px solid var(--linea); }
.enc .eyebrow { display: flex; align-items: center; gap: 12px; font-size: 0.7rem; letter-spacing: 0.17em; text-transform: uppercase;
    color: var(--tinta2); font-weight: 600; }
.enc .eyebrow::before { content: ""; width: 30px; height: 7px; border-radius: 4px; flex: none;
    background: linear-gradient(90deg, var(--rosa) 0 50%, var(--amarillo) 50% 100%); }
.enc .titulo { font-size: 2.9rem; font-weight: 700; letter-spacing: -0.03em; line-height: 1.04; margin-top: 0.55rem; color: var(--tinta); }
.secc { display: flex; align-items: center; gap: 16px; margin: 2.6rem 0 1.1rem; font-size: 0.72rem; letter-spacing: 0.17em;
    text-transform: uppercase; font-weight: 700; color: var(--tinta); }
.secc::after { content: ""; flex: 1; height: 1px; background: var(--linea); }

/* ---------- resumen */
.bento { display: grid; grid-template-columns: 1.75fr 1fr; gap: 16px; }
.b-grande { background: var(--rosa); border-radius: 26px; padding: 30px 32px 28px; }
.b-grande .n { font-size: 5rem; font-weight: 700; letter-spacing: -0.045em; line-height: 0.92; color: var(--tinta); }
.b-grande .t { font-size: 0.92rem; color: #5E4A56; margin-top: 8px; }
.pulso { display: flex; gap: 3px; height: 14px; margin: 28px 0 14px; }
.pulso span { display: block; height: 100%; border-radius: 7px; }
.leyenda { display: flex; flex-wrap: wrap; gap: 8px 24px; font-size: 0.84rem; color: #4F3F49; }
.leyenda i { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 7px; }
.leyenda b { font-weight: 700; color: var(--tinta); }
.b-lado { display: grid; grid-template-rows: 1fr 1fr; gap: 16px; }
.b-chico { border-radius: 26px; padding: 22px 26px; display: flex; flex-direction: column; justify-content: space-between; }
.b-amarillo { background: var(--amarillo); }
.b-borde { background: var(--papel); border: 1px solid var(--linea); }
.b-chico .n { font-size: 3rem; font-weight: 700; letter-spacing: -0.04em; line-height: 1; color: var(--tinta); }
.b-chico .t { font-size: 0.88rem; color: #5B4F3A; margin-top: 6px; }
.b-borde .t { color: var(--tinta2); }
.b-chico .d { font-size: 0.78rem; color: #7A6B4A; margin-top: 10px; }
.b-borde .d { color: var(--tinta2); }

/* ---------- alertas (coral: lo único que pide atención) */
.alerta { background: #FFF1EE; border-left: 5px solid var(--coral); border-radius: 6px 18px 18px 6px; padding: 18px 22px; margin-bottom: 12px; }
.alerta .cab { font-size: 0.7rem; color: #A5503F; letter-spacing: 0.14em; text-transform: uppercase; font-weight: 700; }
.alerta .tit { font-family: 'Bricolage Grotesque', sans-serif; font-size: 1.3rem; font-weight: 600; color: var(--tinta); margin: 5px 0 6px; }
.alerta .txt { color: #4E4350; line-height: 1.55; }
.alerta .ej { color: #7A6D73; font-size: 0.88rem; margin: 10px 0 0; font-style: italic; }
.sinalerta { background: #E8F3EA; border-radius: 18px; padding: 16px 22px; color: #36634A; }

/* ---------- gráfico */
.grafico { background: var(--papel); border: 1px solid var(--linea); border-radius: 24px; padding: 22px 24px 12px; }
.grafico .tit { font-size: 0.84rem; color: var(--tinta2); font-weight: 600; }
.grafico .leg { display: flex; flex-wrap: wrap; gap: 6px 22px; margin: 10px 0 12px; font-size: 0.84rem; color: var(--tinta); font-weight: 500; }
.grafico .leg i { display: inline-block; width: 18px; height: 4px; border-radius: 2px; margin-right: 8px; vertical-align: middle; }
.grafico svg text { font-size: 11px; fill: #8D8191; font-family: 'Plus Jakarta Sans', sans-serif; }

/* ---------- reseñas */
.conteo { color: var(--tinta2); font-size: 0.88rem; margin: 0.4rem 0 0.2rem; }
.conteo b { color: var(--tinta); font-size: 1.05rem; }
.lista { border-top: 1px solid var(--linea); margin-top: 0.4rem; }
.resena { display: grid; grid-template-columns: 124px 1fr auto; gap: 22px; padding: 18px 2px; border-bottom: 1px solid var(--linea); align-items: start; }
.resena .meta { font-size: 0.74rem; color: var(--tinta2); line-height: 1.5; }
.resena .meta b { display: block; color: var(--tinta); font-size: 0.82rem; font-weight: 700; }
.resena .txt { color: var(--tinta); line-height: 1.58; font-size: 0.95rem; }
.resena .chips { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
.chip { display: inline-flex; align-items: center; gap: 7px; border-radius: 999px; padding: 4px 12px; font-size: 0.74rem; font-weight: 700; white-space: nowrap; }
.chip i { width: 7px; height: 7px; border-radius: 50%; }
.c-pos { background: #DDEFE2; color: #2D6746; } .c-pos i { background: #4F9A72; }
.c-neg { background: #FADAD5; color: #8A382F; } .c-neg i { background: var(--coral); }
.c-neu { background: #F1E9DC; color: #66563F; } .c-neu i { background: #B79F7A; }
.c-tema { background: transparent; border: 1px solid var(--linea); color: var(--tinta2); font-weight: 600; }
.c-rev { background: var(--amarillo); color: #5A4812; }

/* ---------- resumen por semana */
.semh { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 6px 20px; margin: 0.6rem 0 1.2rem; }
.semh .rango { font-size: 1.9rem; font-weight: 700; letter-spacing: -0.02em; }
.semh .meta { color: var(--tinta2); font-size: 0.9rem; }
.sem { background: var(--papel); border: 1px solid var(--linea); border-radius: 24px; overflow: hidden; }
.sem .fila { display: grid; grid-template-columns: 1.25fr 0.75fr 0.8fr 0.8fr 0.8fr 2.3fr 0.95fr; gap: 14px; align-items: center;
    padding: 18px 26px; border-bottom: 1px solid var(--linea); font-size: 0.93rem; font-variant-numeric: tabular-nums; }
.sem .fila:last-child { border-bottom: none; }
.sem .cab { background: var(--amarillo2); font-size: 0.66rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--tinta2);
    font-weight: 700; padding-top: 13px; padding-bottom: 13px; }
.sem .tema { font-size: 1.1rem; font-weight: 600; }
.barra { position: relative; height: 9px; border-radius: 5px; background: #F1E9DC; }
.barra span { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 5px; }
.barra em { position: absolute; top: -4px; bottom: -4px; width: 2px; background: var(--tinta); border-radius: 1px; }
.barra-t { font-size: 0.76rem; color: var(--tinta2); margin-top: 7px; }
.estado { font-size: 0.74rem; font-weight: 700; border-radius: 999px; padding: 4px 12px; justify-self: start; }
.e-ok { background: #E3F0E7; color: #35644A; } .e-alerta { background: var(--coral); color: #fff; }

/* ---------- probar una reseña */
.res-panel { border-radius: 26px; padding: 28px 30px; min-height: 300px; }
.res-panel .etq { font-size: 0.68rem; letter-spacing: 0.17em; text-transform: uppercase; font-weight: 700; color: rgba(42, 34, 48, 0.55); }
.res-panel .grande { font-size: 3rem; font-weight: 700; letter-spacing: -0.035em; line-height: 1.02; margin: 8px 0 6px; color: var(--tinta); }
.res-panel .tema { font-size: 1.1rem; font-weight: 600; color: var(--tinta); }
.res-panel .seg { font-size: 0.88rem; color: #4D4352; margin-top: 4px; }
.meter { margin-top: 24px; display: flex; flex-direction: column; gap: 10px; }
.meter .row { display: grid; grid-template-columns: 74px 1fr 40px; gap: 12px; align-items: center; font-size: 0.8rem; color: #4D4352; }
.meter .pista { height: 8px; border-radius: 4px; background: rgba(42, 34, 48, 0.1); overflow: hidden; }
.meter .pista span { display: block; height: 100%; border-radius: 4px; background: var(--tinta); }
.res-panel .pie { margin-top: 22px; font-size: 0.86rem; color: #4D4352; line-height: 1.5; }
.r-positiva { background: #DDEFE2; } .r-negativa { background: #FADAD5; } .r-neutra { background: #F1E9DC; }
.res-panel.vacio { background: transparent; border: 1.5px dashed #D9C9BB; }
.res-panel.vacio .esq { margin-top: 28px; display: flex; flex-direction: column; gap: 14px; }
.res-panel.vacio .esq span { display: block; height: 12px; border-radius: 6px; background: #EFE4D6; }
.res-panel.vacio .esq span:nth-child(1) { width: 55%; height: 30px; } .res-panel.vacio .esq span:nth-child(2) { width: 38%; }
.res-panel.vacio .esq span:nth-child(3) { width: 80%; } .res-panel.vacio .esq span:nth-child(4) { width: 66%; }
.res-panel.aviso { background: var(--amarillo2); }
.res-panel.aviso .msg { font-size: 1.05rem; line-height: 1.5; margin-top: 12px; color: var(--tinta); }
.nota { color: #9A8E9E; font-size: 0.82rem; margin-top: 1.6rem; }

/* ---------- demostración técnica */
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 1.4rem 0 0.4rem; }
.kpi { border-radius: 20px; padding: 18px 20px; }
.kpi:nth-child(odd) { background: var(--rosa2); } .kpi:nth-child(even) { background: var(--amarillo2); }
.kpi .n { font-size: 2.1rem; font-weight: 700; letter-spacing: -0.03em; line-height: 1; }
.kpi .t { font-size: 0.78rem; color: var(--tinta2); margin-top: 8px; }

/* ---------- controles de Streamlit con el mismo lenguaje */
.stApp label p { font-size: 0.78rem; font-weight: 700; color: var(--tinta2); letter-spacing: 0.02em; }
[data-baseweb="select"] > div, [data-baseweb="input"] > div, [data-baseweb="base-input"] { background: var(--papel) !important;
    border-color: var(--linea) !important; border-radius: 14px !important; }
.stTextArea textarea { background: var(--papel); border: 1px solid var(--linea); border-radius: 18px; font-size: 1rem; line-height: 1.6; padding: 16px 18px; }
[data-testid="stForm"] { border: none; padding: 0; }
button[kind="primary"], [data-testid="stBaseButton-primary"], [data-testid="stFormSubmitButton"] button {
    background: var(--tinta); color: #FBF6EE; border: none; border-radius: 999px; font-weight: 700; padding: 0.55rem 1.6rem; }
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover, [data-testid="stFormSubmitButton"] button:hover {
    background: #433650; color: #FFFFFF; }
.stButton > button, .stDownloadButton > button { border-radius: 999px; border: 1px solid #D9C9BB; background: var(--papel); color: var(--tinta);
    font-weight: 600; padding: 0.45rem 1.4rem; }
[data-baseweb="tab-list"] { gap: 26px; border-bottom: 1px solid var(--linea); }
button[data-baseweb="tab"] { background: transparent; padding-left: 0; padding-right: 0; }
button[data-baseweb="tab"] p { font-weight: 600; color: var(--tinta2); font-size: 0.93rem; }
button[data-baseweb="tab"][aria-selected="true"] p { color: var(--tinta); }
[data-baseweb="tab-highlight"] { background: #E3A92B !important; height: 3px !important; }
[data-testid="stExpander"] { border: 1px solid var(--linea); border-radius: 18px; background: var(--papel); }
[data-testid="stExpander"] summary p { font-weight: 600; color: var(--tinta); font-size: 0.9rem; letter-spacing: 0; }
[data-testid="stMarkdownContainer"] table { border-collapse: collapse; width: 100%; font-size: 0.86rem; }
[data-testid="stMarkdownContainer"] th { background: var(--amarillo2); color: var(--tinta2); font-size: 0.7rem; letter-spacing: 0.1em;
    text-transform: uppercase; text-align: left; padding: 10px 12px; border: none; border-bottom: 1px solid var(--linea); }
[data-testid="stMarkdownContainer"] td { padding: 10px 12px; border: none; border-bottom: 1px solid var(--linea); vertical-align: top; }
@media (max-width: 860px) {
    .bento { grid-template-columns: 1fr; }
    .resena { grid-template-columns: 1fr; gap: 8px; } .resena .chips { flex-direction: row; flex-wrap: wrap; align-items: flex-start; }
    .sem .fila { grid-template-columns: 1fr 1fr; }
    .enc .titulo { font-size: 2.2rem; }
}
</style>
"""
st.markdown(ESTILO, unsafe_allow_html=True)

MARCA = (
    '<div class="marca"><svg width="42" height="42" viewBox="0 0 42 42" aria-hidden="true">'
    '<rect width="42" height="42" rx="13" fill="#FBE6A2"/>'
    '<polyline points="7,23 14,23 18,12 24,32 28,20 35,20" fill="none" stroke="#2A2230" stroke-width="2.7" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    '<div><div class="m1">Review<b>Pulse</b></div><div class="m2">Hotel piloto</div></div></div>'
)

TEMAS = {"limpieza": "Limpieza", "servicio": "Servicio", "ubicacion": "Ubicación", "precio": "Precio"}
COLOR_TEMA = {"Limpieza": "#3F8FAE", "Servicio": "#D4577F", "Ubicación": "#5FA67F", "Precio": "#D9A21B"}
SENT = {"positiva": "Positiva", "negativa": "Negativa", "neutra": "Neutra"}
CLASE_SENT = {"Positiva": "c-pos", "Negativa": "c-neg", "Neutra": "c-neu"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
MOTIVOS = {"texto_vacio_o_ruido": "Texto demasiado corto o sin contenido", "sin_fecha": "Sin fecha de publicación",
           "idioma_en": "Escrita en inglés", "idioma_pt": "Escrita en portugués", "idioma_fr": "Escrita en francés",
           "idioma_desconocido": "Idioma no reconocido"}
POR_PAGINA = 12


@st.cache_resource
def modelo():
    return ClasificadorSentimiento.cargar()


cfg_archivo = json.loads((RAIZ / "config" / "config.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ utilidades de presentación
def rango_semana(s: int):
    """Fechas de inicio y fin de la semana s, tomadas del mismo texto que usa el agente en sus reportes."""
    d1, m1, d2, m2, y = map(int, re.search(r"\((\d\d)/(\d\d)–(\d\d)/(\d\d)/(\d{4})\)", texto_semana(s)).groups())
    return pd.Timestamp(y, m1, d1), pd.Timestamp(y, m2, d2)


def rango_texto(s: int) -> str:
    a, b = rango_semana(s)
    if a.month == b.month:
        return f"{a.day} al {b.day} de {MESES[b.month - 1]}"
    return f"{a.day} de {MESES[a.month - 1]} al {b.day} de {MESES[b.month - 1]}"


def fecha_corta(ts) -> str:
    return f"{ts.day:02d} {MESES[ts.month - 1][:3]} {ts.year}"


def miles(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def seguridad(c: float, umbral: float) -> str:
    return "Alta" if c >= 0.8 else ("Media" if c >= umbral else "Baja")


def encabezado(eyebrow: str, titulo: str):
    st.markdown(f'<div class="enc"><div class="eyebrow">{html.escape(eyebrow)}</div>'
                f'<div class="titulo">{html.escape(titulo)}</div></div>', unsafe_allow_html=True)


def seccion(texto: str):
    st.markdown(f'<div class="secc">{html.escape(texto)}</div>', unsafe_allow_html=True)


def html_alerta(a: dict, etiqueta: str | None = None) -> str:
    tema = TEMAS[a["tema"]].lower()
    m = re.search(r"Ejemplos: (.*)$", a["mensaje"])
    ejemplos = [e.strip(" “”") for e in m.group(1).split(" | ")] if m else []
    enviada = pd.Timestamp(a["enviada_en"])
    tarde = a.get("tipo") not in (None, "a_tiempo")
    txt = (f"Entre el {rango_texto(a['semana'])}, el {a['proporcion']:.0%} de las reseñas sobre {tema} fueron "
           f"negativas. Lo habitual en las seis semanas anteriores era {a['promedio']:.0%}.")
    if tarde:
        txt += " Esta alerta se detectó con retraso."
    ej = ('<p class="ej">' + " · ".join(f"“{html.escape(e)}”" for e in ejemplos[:2]) + "</p>") if ejemplos else ""
    cab = f"Alerta enviada el {enviada.day} de {MESES[enviada.month - 1]}"
    if etiqueta:
        cab = f"{etiqueta} · enviada el {enviada.day} de {MESES[enviada.month - 1]}"
    return (f'<div class="alerta"><div class="cab">{cab}</div>'
            f'<div class="tit">Las quejas sobre {tema} subieron</div><div class="txt">{txt}</div>{ej}</div>')


def mostrar_alertas(alertas: list, vacio: str):
    if alertas:
        for a in alertas:
            st.markdown(html_alerta(a), unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="sinalerta">{vacio}</div>', unsafe_allow_html=True)


def tabla_resenas(df: pd.DataFrame, umbral: float) -> pd.DataFrame:
    t = df.sort_values("fecha_dt", ascending=False)
    return pd.DataFrame({
        "Fecha": t["fecha_dt"].map(fecha_corta), "Plataforma": t["plataforma"], "Reseña": t["texto"],
        "Sentimiento": t["polaridad"].map(SENT), "Tema": t["tema"].map(TEMAS),
        "Seguridad": t["confianza"].map(lambda c: seguridad(c, umbral)),
    }).reset_index(drop=True)


def html_resenas(t: pd.DataFrame) -> str:
    filas = []
    for r in t.itertuples(index=False):
        rev = ('<span class="chip c-rev" title="El agente no estaba seguro: queda marcada para revisión manual">'
               'Revisión manual</span>') if r.Seguridad == "Baja" else ""
        filas.append(
            f'<div class="resena"><div class="meta"><b>{r.Fecha}</b>{html.escape(r.Plataforma)}</div>'
            f'<div class="txt">{html.escape(r.Reseña)}</div>'
            f'<div class="chips"><span class="chip {CLASE_SENT[r.Sentimiento]}"><i></i>{r.Sentimiento}</span>'
            f'<span class="chip c-tema">{r.Tema}</span>{rev}</div></div>')
    return '<div class="lista">' + "".join(filas) + "</div>"


def svg_temas(df: pd.DataFrame, alertas: list, titulo: str) -> str:
    """Gráfico de líneas propio: % de reseñas negativas por tema y semana, con las alertas marcadas."""
    d = df.assign(neg=df["polaridad"].eq("negativa"))
    piv = (d.groupby(["semana", "tema"])["neg"].mean().unstack().fillna(0) * 100).rename(columns=TEMAS)
    semanas = list(piv.index)
    W, H, ml, mr, mt, mb = 760, 292, 46, 18, 26, 34
    ymax = max(50, int(-(-float(piv.max().max()) // 25) * 25))

    def X(i):
        return ml + (W - ml - mr) * i / max(len(semanas) - 1, 1)

    def Y(v):
        return mt + (H - mt - mb) * (1 - v / ymax)

    p = []
    for g in range(0, ymax + 1, 25):
        p.append(f'<line x1="{ml}" x2="{W - mr}" y1="{Y(g):.1f}" y2="{Y(g):.1f}" stroke="#EADFD3" stroke-width="1"/>'
                 f'<text x="{ml - 10}" y="{Y(g) + 4:.1f}" text-anchor="end">{g}%</text>')
    for i, s in enumerate(semanas):
        if i % 2 == 0:
            a = rango_semana(s)[0]
            p.append(f'<text x="{X(i):.1f}" y="{H - 10}" text-anchor="middle">{a.day} {MESES[a.month - 1][:3]}</text>')
    for a in alertas:
        if a["semana"] in semanas:
            x = X(semanas.index(a["semana"]))
            p.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{mt - 4}" y2="{H - mb}" stroke="#DB6B5E" stroke-width="1.4" '
                     f'stroke-dasharray="4 4"/><text x="{x:.1f}" y="{mt - 10}" text-anchor="middle" '
                     f'style="fill:#B4503F;font-weight:700">Alerta</text>')
    for tema in piv.columns:
        col = COLOR_TEMA[tema]
        pts = [(X(i), Y(v)) for i, v in enumerate(piv[tema])]
        path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
        p.append(f'<path d="{path}" fill="none" stroke="{col}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>')
        p.append(f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="4.5" fill="{col}"/>')
        for i, (x, y) in enumerate(pts):
            a = rango_semana(semanas[i])[0]
            p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="transparent"><title>{tema} · semana del {a.day} '
                     f'{MESES[a.month - 1][:3]}: {piv[tema].iloc[i]:.0f}% negativas</title></circle>')
    leyenda = "".join(f'<span><i style="background:{COLOR_TEMA[t]}"></i>{t}</span>' for t in piv.columns)
    return (f'<div class="grafico"><div class="tit">{html.escape(titulo)}</div><div class="leg">{leyenda}</div>'
            f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" style="display:block">{"".join(p)}</svg></div>')


def leer_reporte(texto: str):
    """Convierte la tabla del resumen semanal (markdown) en un DataFrame legible, o None si cambia el formato."""
    filas = [[c.strip() for c in l.strip().strip("|").split("|")] for l in texto.splitlines()
             if l.startswith("|") and not l.startswith("|---")]
    if len(filas) < 2:
        return None
    t = pd.DataFrame(filas[1:], columns=filas[0])
    t["Alerta"] = t["Alerta"].str.replace("⚠️ ", "", regex=False)
    return t.rename(columns={"Promedio histórico": "Lo habitual"})


def _pct(txt) -> float:
    try:
        return float(str(txt).strip().rstrip("%").replace(",", "."))
    except ValueError:
        return 0.0


def html_semana(t: pd.DataFrame) -> str:
    filas = ['<div class="fila cab"><div>Tema</div><div>Reseñas</div><div>Positivas</div><div>Neutras</div>'
             '<div>Negativas</div><div>% negativas · lo habitual</div><div>Estado</div></div>']
    for r in t.to_dict("records"):
        neg, hab = _pct(r["% negativas"]), _pct(r["Lo habitual"])
        color = COLOR_TEMA.get(r["Tema"], "#D4577F")
        alerta = str(r["Alerta"]).strip().lower() not in ("no", "")
        estado = '<span class="estado e-alerta">Alerta</span>' if alerta else '<span class="estado e-ok">Normal</span>'
        filas.append(
            f'<div class="fila"><div class="tema">{html.escape(r["Tema"])}</div><div>{r["Reseñas"]}</div>'
            f'<div>{r["Positivas"]}</div><div>{r["Neutras"]}</div><div>{r["Negativas"]}</div>'
            f'<div><div class="barra"><span style="width:{min(neg, 100):.0f}%;background:{color}"></span>'
            f'<em style="left:{min(hab, 100):.0f}%"></em></div>'
            f'<div class="barra-t"><b>{r["% negativas"]}</b> · habitual {r["Lo habitual"]}</div></div>{estado}</div>')
    return '<div class="sem">' + "".join(filas) + "</div>"


# ------------------------------------------------------------------ datos del hotel piloto
@st.cache_resource(show_spinner="Analizando las reseñas del hotel…")
def historial_hotel():
    """El agente procesa una vez el historial simulado del hotel piloto (escenario E02, semilla 11)."""
    with tempfile.TemporaryDirectory() as tmp:
        entorno = EntornoHotel(ESCENARIOS["E02"], 11)
        agente = ReviewPulseAgent(entorno, Path(tmp), dict(cfg_archivo), modelo())
        res = agente.ejecutar()
        reportes = {int(p.stem.split("_")[1]): p.read_text(encoding="utf-8")
                    for p in sorted((Path(tmp) / "reportes").glob("*.md"))}
    df = pd.DataFrame(res["resenas"])
    df["fecha_dt"] = pd.to_datetime(df["fecha"])
    return dict(df=df, alertas=res["alertas"], reportes=reportes, descartadas=res["descartadas"],
                umbral=cfg_archivo["umbral_confianza"])


# ------------------------------------------------------------------ páginas del panel
def pagina_resumen(h):
    df = h["df"]
    encabezado("Hotel piloto · datos de demostración", "Resumen")
    n = len(df)
    pos, neu, neg = (df["polaridad"] == "positiva").mean(), (df["polaridad"] == "neutra").mean(), (df["polaridad"] == "negativa").mean()
    plat = df["plataforma"].value_counts(normalize=True)
    revision = int((df["confianza"] < h["umbral"]).sum())
    if h["alertas"]:
        ult = h["alertas"][-1]
        d_alertas = f"Última: {TEMAS[ult['tema']].lower()}, semana del {rango_texto(ult['semana'])}"
    else:
        d_alertas = "El tono se ha mantenido normal"
    st.markdown(
        f'<div class="bento"><div class="b-grande"><div class="n">{miles(n)}</div>'
        f'<div class="t">reseñas analizadas · {fecha_corta(df["fecha_dt"].min())} a {fecha_corta(df["fecha_dt"].max())}</div>'
        f'<div class="pulso"><span style="flex:{max(pos, 0.01):.3f};background:#5FA67F"></span>'
        f'<span style="flex:{max(neu, 0.01):.3f};background:#F6EBDD"></span>'
        f'<span style="flex:{max(neg, 0.01):.3f};background:#DB6B5E"></span></div>'
        f'<div class="leyenda"><span><i style="background:#5FA67F"></i><b>{pos:.0%}</b> positivas</span>'
        f'<span><i style="background:#F6EBDD"></i><b>{neu:.0%}</b> neutras</span>'
        f'<span><i style="background:#DB6B5E"></i><b>{neg:.0%}</b> negativas</span>'
        f'<span>{" · ".join(f"{k} {v:.0%}" for k, v in plat.items())}</span></div></div>'
        f'<div class="b-lado"><div class="b-chico b-amarillo"><div><div class="n">{len(h["alertas"])}</div>'
        f'<div class="t">alertas enviadas al gerente</div></div><div class="d">{d_alertas}</div></div>'
        f'<div class="b-chico b-borde"><div><div class="n">{revision}</div><div class="t">para revisión manual</div></div>'
        f'<div class="d">Reseñas en las que el agente no estaba seguro</div></div></div></div>', unsafe_allow_html=True)

    seccion("Alertas")
    mostrar_alertas(h["alertas"], "No se ha enviado ninguna alerta: el tono de las reseñas se ha mantenido dentro de lo normal.")

    seccion("Cómo va cada tema")
    st.markdown(svg_temas(df, h["alertas"], "Porcentaje de reseñas negativas por semana"), unsafe_allow_html=True)

    seccion("Reseñas recientes")
    st.markdown(html_resenas(tabla_resenas(df, h["umbral"]).head(6)), unsafe_allow_html=True)


def pagina_resenas(h):
    encabezado("Historial", "Reseñas del hotel")
    t = tabla_resenas(h["df"], h["umbral"])
    c1, c2, c3, c4 = st.columns([1, 1, 1, 0.7])
    sent = c1.selectbox("Sentimiento", ["Todos"] + list(SENT.values()))
    tema = c2.selectbox("Tema", ["Todos"] + list(TEMAS.values()))
    plat = c3.selectbox("Plataforma", ["Todas", "TripAdvisor", "Google"])
    f = t
    if sent != "Todos":
        f = f[f["Sentimiento"] == sent]
    if tema != "Todos":
        f = f[f["Tema"] == tema]
    if plat != "Todas":
        f = f[f["Plataforma"] == plat]
    paginas = max(1, -(-len(f) // POR_PAGINA))
    pag = c4.number_input(f"Página (de {paginas})", 1, paginas, 1)
    st.markdown(f'<div class="conteo"><b>{miles(len(f))}</b> de {miles(len(t))} reseñas</div>', unsafe_allow_html=True)
    st.markdown(html_resenas(f.iloc[(int(pag) - 1) * POR_PAGINA: int(pag) * POR_PAGINA]), unsafe_allow_html=True)
    st.write("")
    st.download_button("Descargar esta tabla (CSV)", f.to_csv(index=False).encode("utf-8"), "resenas_hotel_piloto.csv")
    desc = pd.Series([MOTIVOS.get(d["motivo"], d["motivo"]) for d in h["descartadas"]]).value_counts()
    with st.expander(f"Reseñas que el agente no pudo analizar ({int(desc.sum())})"):
        st.dataframe(desc.rename_axis("Motivo").reset_index(name="Cantidad"), hide_index=True, width="stretch")


def pagina_semanas(h):
    encabezado("Informe semanal", "Resumen por semana")
    semanas = sorted(h["reportes"])
    con_alerta = [a["semana"] for a in h["alertas"] if a["semana"] in semanas]
    s = st.selectbox("Semana", semanas, index=semanas.index(con_alerta[0]) if con_alerta else len(semanas) - 1,
                     format_func=lambda x: f"Del {rango_texto(x)}" + ("  ·  con alerta" if x in con_alerta else ""))
    texto = h["reportes"][s]
    resumen = re.search(r"Reseñas clasificadas: ([\d.]+) · Para revisión manual: (\d+)", texto)
    meta = (f"{float(resumen.group(1)):g} reseñas analizadas · {resumen.group(2)} para revisión manual") if resumen else ""
    st.markdown(f'<div class="semh"><div class="rango">Del {rango_texto(s)}</div><div class="meta">{meta}</div></div>',
                unsafe_allow_html=True)
    tabla = leer_reporte(texto)
    if tabla is not None:
        st.markdown(html_semana(tabla), unsafe_allow_html=True)
    else:
        st.markdown(texto)
    seccion("Alertas de la semana")
    mostrar_alertas([a for a in h["alertas"] if a["semana"] == s], "Sin alertas: la variación estuvo dentro de lo normal.")


def html_resultado(r) -> str:
    if r is None:
        return ('<div class="res-panel vacio"><div class="etq">Resultado</div>'
                '<div class="esq"><span></span><span></span><span></span><span></span></div></div>')
    if "error" in r:
        return f'<div class="res-panel aviso"><div class="etq">Sin resultado</div><div class="msg">{r["error"]}</div></div>'
    p, umbral = r["p"], r["umbral"]
    destino = ("Quedaría marcada para revisión manual y contaría la mitad en el resumen semanal."
               if p.confianza < umbral else "Se sumaría al conteo de la semana.")
    filas = "".join(
        f'<div class="row"><span>{SENT[k]}</span><div class="pista"><span style="width:{p.prob_polaridad.get(k, 0) * 100:.0f}%">'
        f'</span></div><span>{p.prob_polaridad.get(k, 0):.0%}</span></div>' for k in ("positiva", "neutra", "negativa"))
    return (f'<div class="res-panel r-{p.polaridad}"><div class="etq">Resultado</div>'
            f'<div class="grande">{SENT[p.polaridad]}</div><div class="tema">Sobre {TEMAS[p.tema].lower()}</div>'
            f'<div class="seg">Seguridad {seguridad(p.confianza, umbral).lower()} · {p.confianza:.0%}</div>'
            f'<div class="meter">{filas}</div><div class="pie">{destino}</div></div>')


def pagina_probar():
    encabezado("Clasificador", "Probar una reseña")
    izq, der = st.columns([3, 2], gap="large")
    with izq:
        with st.form("form_prueba"):
            texto = st.text_area("Reseña", key="texto_prueba", height=250, placeholder="Escribe aquí una reseña en español…")
            enviar = st.form_submit_button("Analizar reseña", type="primary")
    if enviar:
        ok, limpio, motivo = validar({"texto": texto, "fecha": "2026-01-01"})
        if not ok:
            if motivo == "texto_vacio_o_ruido":
                msg = "La reseña es muy corta. Escribe al menos tres palabras para poder analizarla."
            elif motivo.startswith("idioma_"):
                msg = "El agente solo analiza reseñas en español, y esta parece estar escrita en otro idioma."
            else:
                msg = "El agente no pudo leer esta reseña."
            st.session_state["resultado_prueba"] = dict(error=msg)
        else:
            p = modelo().predecir([limpio])[0]
            st.session_state["resultado_prueba"] = dict(p=p, umbral=cfg_archivo["umbral_confianza"])
    with der:
        st.markdown(html_resultado(st.session_state.get("resultado_prueba")), unsafe_allow_html=True)
    st.markdown('<p class="nota">El agente aprendió con reseñas de hotel simuladas; con palabras que no conoce puede '
                'equivocarse. Por eso siempre muestra qué tan seguro está.</p>', unsafe_allow_html=True)


# ------------------------------------------------------------------ demostración técnica
def html_kpis(items) -> str:
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="n">{v}</div><div class="t">{t}</div></div>' for v, t in items) + "</div>"


def pagina_tecnica():
    encabezado("Agente", "Demostración técnica")
    tab_demo, tab_pruebas, tab_casos = st.tabs(["Ejecutar un escenario", "Resultados de las pruebas", "Casos sugeridos"])

    with tab_demo:
        cfg = dict(cfg_archivo)
        with st.expander("Ajustes de las alertas (lo que decide el gerente)"):
            st.caption("Son los umbrales que el agente lee como configuración. Cámbialos y vuelve a ejecutar para "
                       "ver cómo cambian las alertas.")
            cfg["alfa"] = st.number_input("Qué tan raro debe ser el aumento (α)", 0.001, 0.2, float(cfg["alfa"]), 0.005,
                                          format="%.3f", help="Más bajo = exige más evidencia y alerta menos.")
            cfg["delta_minimo"] = st.slider("Aumento mínimo de reseñas negativas", 0.0, 0.5, float(cfg["delta_minimo"]),
                                            0.01, help="Cuánto debe subir el porcentaje de negativas frente a lo habitual.")
            cfg["z_minimo"] = st.slider("Distancia mínima al promedio (z)", 0.0, 5.0, float(cfg.get("z_minimo", 0.0)),
                                        0.25, help="0 = no se usa este criterio.")
            cfg["min_negativas"] = st.slider("Mínimo de reseñas negativas del tema", 1, 10, int(cfg["min_negativas"]),
                                             help="Cantidad mínima de negativas esa semana para poder alertar.")
            cfg["umbral_confianza"] = st.slider("Seguridad mínima del agente", 0.3, 0.9, float(cfg["umbral_confianza"]),
                                                0.05, help="Si está menos seguro que esto, la reseña va a revisión "
                                                           "manual y cuenta la mitad.")
        c1, c2 = st.columns([2, 1])
        eid = c1.selectbox("Escenario", list(ESCENARIOS), format_func=lambda e: f"{e} · {ESCENARIOS[e].nombre}",
                           help="Situación que simula el entorno del hotel.")
        semilla = c2.number_input("Semilla", 1, 9999, 11, help="Fija el azar del simulador: con la misma semilla salen las mismas reseñas.")
        st.caption(f"**{ESCENARIOS[eid].tipo.capitalize()}** · {ESCENARIOS[eid].descripcion}")
        if st.button("Ejecutar desde cero", type="primary"):
            with tempfile.TemporaryDirectory() as tmp, st.spinner("El agente está procesando las reseñas…"):
                entorno = EntornoHotel(ESCENARIOS[eid], int(semilla))
                agente = ReviewPulseAgent(entorno, Path(tmp), cfg, modelo())
                res = agente.ejecutar()
                met = evaluar_corrida(entorno, res)
                eventos = agente.log.eventos
                reportes = {int(p.stem.split("_")[1]): p.read_text(encoding="utf-8")
                            for p in sorted((Path(tmp) / "reportes").glob("*.md"))}
                log_txt = (Path(tmp) / "log_ejecucion.jsonl").read_text(encoding="utf-8")
            st.session_state["corrida"] = dict(res=res, met=met, eventos=eventos, reportes=reportes, log=log_txt,
                                               eid=eid, semilla=semilla, verdad=entorno.verdad)

        if "corrida" in st.session_state:
            c = st.session_state["corrida"]
            met, res = c["met"], c["res"]
            st.markdown(html_kpis([
                (miles(met["resenas_clasificadas"]), "Reseñas clasificadas"),
                (miles(met["resenas_descartadas"]), "Descartadas"),
                (f"{met['reportes_a_tiempo']}/{met['semanas_cerradas']}", "Reportes a tiempo"),
                (f"{met['detectados_24h']}/{met['incidentes_relevantes']}", "Incidentes detectados ≤ 24 h"),
                (str(met["alertas_fp"]), "Falsos positivos"),
            ]), unsafe_allow_html=True)

            df = pd.DataFrame(res["resenas"])
            if not df.empty:
                seccion("Reseñas negativas por tema y semana")
                st.markdown(svg_temas(df, res["alertas"], "Porcentaje de reseñas negativas por semana"), unsafe_allow_html=True)

            seccion("Alertas enviadas al gerente")
            if res["alertas"]:
                for a in res["alertas"]:
                    real = c["verdad"][a["semana"]]["incidentes"].get(a["tema"])
                    st.markdown(html_alerta(a, "Incidente real" if real == "relevante" else "Falso positivo"),
                                unsafe_allow_html=True)
            else:
                st.markdown('<div class="sinalerta">Sin alertas en esta corrida.</div>', unsafe_allow_html=True)

            seccion("Registro de ejecución · percepción → decisión → acción")
            ev = pd.DataFrame(c["eventos"])
            fases = st.multiselect("Fases", ["PERCEPCION", "DECISION", "ACCION", "SISTEMA"],
                                   ["PERCEPCION", "DECISION", "ACCION"])
            st.dataframe(ev[ev["fase"].isin(fases)][["ts_simulado", "fase", "evento"] +
                         [x for x in ["semana", "motivo", "acciones", "nuevas", "disponibilidad"] if x in ev]],
                         width="stretch", height=320)
            st.download_button("Descargar log (JSONL)", c["log"], f"log_{c['eid']}_s{c['semilla']}.jsonl")

    with tab_pruebas:
        ruta = RAIZ / "salidas" / "pruebas" / "tabla_resultados.md"
        if ruta.exists():
            st.markdown(ruta.read_text(encoding="utf-8"))
        else:
            st.info("Ejecute `python pruebas/ejecutar_pruebas.py` para generar la tabla.")

    with tab_casos:
        st.markdown("""
**Casos de prueba sugeridos**

1. **E02 Incidente de limpieza** (típico): el agente debe alertar la semana 9 dentro de las 24 h.
2. **E04 Temporada alta** (límite): más reseñas pero mismo tono, no debe alertar.
3. **E10 TripAdvisor caído** (falla esperada): el reporte sale a tiempo marcado como incompleto.
4. **E11 Todas las plataformas caídas** (falla esperada): no hay datos al cierre; la alerta llega tarde.
5. En *Probar una reseña*, escriba un texto de una o dos palabras: el agente lo descarta.

Cambie los ajustes de las alertas y vuelva a ejecutar para ver el efecto sobre los falsos positivos.
""")


# ------------------------------------------------------------------ navegación
with st.sidebar:
    st.markdown(MARCA, unsafe_allow_html=True)
    st.markdown('<div class="grupo">Panel</div>', unsafe_allow_html=True)
    vista = st.radio("Menú", ["Resumen", "Reseñas del hotel", "Resumen por semana", "Probar una reseña",
                              "Demostración técnica"], label_visibility="collapsed")

if vista == "Resumen":
    pagina_resumen(historial_hotel())
elif vista == "Reseñas del hotel":
    pagina_resenas(historial_hotel())
elif vista == "Resumen por semana":
    pagina_semanas(historial_hotel())
elif vista == "Probar una reseña":
    pagina_probar()
else:
    pagina_tecnica()
