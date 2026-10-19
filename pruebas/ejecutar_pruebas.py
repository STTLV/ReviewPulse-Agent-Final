"""Ejecuta todas las pruebas contra las medidas de desempeño (sección 7 del diseño).

Uso:  python pruebas/ejecutar_pruebas.py            (completo: 11 casos M1 + 12 escenarios, 5 repeticiones)
      python pruebas/ejecutar_pruebas.py --rapido   (1 repetición, para la demo en vivo)

Salidas en salidas/pruebas/ (con --rapido, en salidas/pruebas_rapido/):
  m1_clasificacion.csv        una fila por caso y repetición
  escenarios.csv              una fila por escenario y repetición (M2, M3, M4)
  corridas/<E>_s<semilla>/    log_ejecucion.jsonl, memoria.db, reportes/ y bandeja_salida.jsonl de cada corrida
  resumen.json                medias, desviaciones y veredicto por medida
  tabla_resultados.md         tabla obligatoria de la Fase 3
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import statistics as st
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from reviewpulse.agente import ReviewPulseAgent  # noqa: E402
from reviewpulse.corpus import (ENTRADAS_INVALIDAS, FRASES, IRONIA, OTROS_IDIOMAS, TEMAS,  # noqa: E402
                                construir_corpus, generar_resena)
from reviewpulse.entorno import EntornoHotel  # noqa: E402
from reviewpulse.escenarios import ESCENARIOS  # noqa: E402
from reviewpulse.evaluacion import evaluar_corrida  # noqa: E402
from reviewpulse.modelo import ClasificadorSentimiento, entrenar_modelo_base  # noqa: E402
from reviewpulse.preprocesamiento import validar  # noqa: E402

SALIDA = RAIZ / "salidas" / "pruebas"
UMBRALES = json.loads((RAIZ / "pruebas" / "umbrales.json").read_text(encoding="utf-8"))


def leer_csv(nombre):
    with (RAIZ / "datos" / nombre).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def sin_tildes(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def con_typos(t, rng):
    letras = list(t)
    for _ in range(max(1, len(t) // 25)):
        i = rng.randrange(1, len(letras) - 2)
        letras[i], letras[i + 1] = letras[i + 1], letras[i]
    return "".join(letras)


# ---------------------------------------------------------------- M1: exactitud de clasificación
def casos_m1(semilla: int):
    rng = random.Random(semilla)
    holdout = leer_csv("evaluacion_manual_holdout.csv")
    desarrollo = leer_csv("evaluacion_manual.csv")
    largas = []
    for _ in range(300):
        t, p = rng.choice(TEMAS), rng.choice(["positiva", "negativa", "neutra"])
        frases = [f for i, f in enumerate(FRASES[t][p]) if i % 4 == 3]
        extra = rng.sample(FRASES[t][p], k=3)
        largas.append({"texto": " ".join(frases + extra) * 2, "tema": t, "polaridad": p})
    cortas = []
    for _ in range(300):
        t, p = rng.choice(TEMAS), rng.choice(["positiva", "negativa", "neutra"])
        cortas.append({"texto": rng.choice([f for i, f in enumerate(FRASES[t][p]) if i % 4 == 3]),
                       "tema": t, "polaridad": p})
    ironia = [{"texto": f, "tema": t, "polaridad": "negativa"} for t, fs in IRONIA.items() for f in fs]
    return [
        ("C01", "Sintético con frases no vistas", "normal", "clasificar", construir_corpus(500, semilla, "evaluacion")),
        ("C02", "Manual de desarrollo (40)", "normal", "clasificar", desarrollo),
        ("C03", "Manual de control, nunca usado al ajustar (40)", "normal", "clasificar", holdout),
        ("C04", "Control en minúsculas y sin tildes", "limite", "clasificar",
         [{**r, "texto": sin_tildes(r["texto"])} for r in holdout]),
        ("C05", "Control con errores de tipeo", "limite", "clasificar",
         [{**r, "texto": con_typos(r["texto"], rng)} for r in holdout]),
        ("C06", "Solo ironía y sarcasmo (12)", "limite", "clasificar", ironia),
        ("C07", "Reseñas largas (>60 palabras)", "limite", "clasificar", largas),
        ("C08", "Reseñas de una sola frase", "limite", "clasificar", cortas),
        ("C09", "Sintético con 30 % de ironía", "limite", "clasificar",
         construir_corpus(500, semilla + 1, "evaluacion", prob_ironia=0.30)),
        ("C10", "Otro idioma: debe descartarse", "falla", "rechazar",
         [{"texto": t, "fecha": "2026-01-01"} for t in OTROS_IDIOMAS]),
        ("C11", "Entradas inválidas: vacías, emojis, HTML, sin fecha", "falla", "rechazar",
         [{"texto": t, "fecha": "2026-01-01"} for t in ENTRADAS_INVALIDAS] +
         [{"texto": "La habitación estaba muy limpia y el personal fue amable.", "fecha": None}]),
    ]


def prueba_m1(semillas):
    filas = []
    for s in semillas:
        modelo = entrenar_modelo_base(semilla=s, guardar=False)  # repetición = reentrenar con otra semilla
        for cid, nombre, tipo, modo, datos in casos_m1(s):
            if modo == "rechazar":
                rechazadas = sum(not validar(r)[0] for r in datos)
                filas.append({"caso": cid, "descripcion": nombre, "tipo": tipo, "semilla": s, "n": len(datos),
                              "exactitud_polaridad": "", "exactitud_tema": "", "confianza_media": "",
                              "tasa_rechazo": round(rechazadas / len(datos), 4), "errores": ""})
                continue
            preds = modelo.predecir([r["texto"] for r in datos])
            ok_p = [p.polaridad == r["polaridad"] for p, r in zip(preds, datos)]
            ok_t = [p.tema == r["tema"] for p, r in zip(preds, datos)]
            errores = [r.get("id", str(i)) for i, (a, b, r) in enumerate(zip(ok_p, ok_t, datos)) if not (a and b)]
            filas.append({"caso": cid, "descripcion": nombre, "tipo": tipo, "semilla": s, "n": len(datos),
                          "exactitud_polaridad": round(sum(ok_p) / len(datos), 4),
                          "exactitud_tema": round(sum(ok_t) / len(datos), 4),
                          "confianza_media": round(st.mean(p.confianza for p in preds), 4),
                          "tasa_rechazo": "", "errores": " ".join(errores[:15])})
        print(f"  M1 semilla {s} lista", flush=True)
    return filas


# ---------------------------------------------------------------- M2, M3, M4: escenarios del agente
def prueba_escenarios(semillas, modelo):
    filas = []
    for eid, esc in ESCENARIOS.items():
        for s in semillas:
            carpeta = SALIDA / "corridas" / f"{eid}_s{s}"
            shutil.rmtree(carpeta, ignore_errors=True)
            entorno = EntornoHotel(esc, s)
            agente = ReviewPulseAgent(entorno, carpeta, modelo=modelo)
            t0 = time.perf_counter()
            resultado = agente.ejecutar()
            m = evaluar_corrida(entorno, resultado)
            filas.append({"escenario": eid, "nombre": esc.nombre, "tipo": esc.tipo, "semilla": s,
                          "segundos": round(time.perf_counter() - t0, 2), **m,
                          "fp_detalle": " ".join(m["fp_detalle"]),
                          "log": str(carpeta.relative_to(RAIZ) / "log_ejecucion.jsonl")})
        print(f"  {eid} listo", flush=True)
    return filas


def media_de(xs):
    xs = [x for x in xs if x not in ("", None)]
    if not xs:
        return None, None
    return st.mean(xs), (st.stdev(xs) if len(xs) > 1 else 0.0)


def resumir(m1, esc):
    U = UMBRALES
    r = {"umbrales": U, "generado_en": datetime.now().isoformat(timespec="seconds"), "m1": {}, "escenarios": {}}
    for cid in dict.fromkeys(f["caso"] for f in m1):
        g = [f for f in m1 if f["caso"] == cid]
        mp, dp = media_de([f["exactitud_polaridad"] for f in g])
        mt, dt = media_de([f["exactitud_tema"] for f in g])
        mr, dr = media_de([f["tasa_rechazo"] for f in g])
        r["m1"][cid] = {"descripcion": g[0]["descripcion"], "tipo": g[0]["tipo"], "n": g[0]["n"],
                        "polaridad_media": mp, "polaridad_de": dp, "tema_media": mt, "tema_de": dt,
                        "rechazo_media": mr, "rechazo_de": dr,
                        "cumple": (mr >= U["M1_rechazo_entradas_invalidas"]) if mr is not None else
                        (mp >= U["M1_exactitud_polaridad"] and mt >= U["M1_exactitud_tema"])}
    for eid in dict.fromkeys(f["escenario"] for f in esc):
        g = [f for f in esc if f["escenario"] == eid]
        det = [f["detectados_24h"] / f["incidentes_relevantes"] for f in g if f["incidentes_relevantes"]]
        rep = [f["reportes_a_tiempo"] / f["semanas_cerradas"] for f in g]
        fp = [f["alertas_fp"] for f in g]
        r["escenarios"][eid] = {
            "nombre": g[0]["nombre"], "tipo": g[0]["tipo"],
            "deteccion_media": media_de(det)[0], "deteccion_de": media_de(det)[1],
            "detectados_tarde_total": sum(f["detectados_tarde"] for f in g),
            "reportes_media": media_de(rep)[0], "reportes_de": media_de(rep)[1],
            "alertas_total": sum(f["alertas_total"] for f in g), "fp_total": sum(fp),
            "fp_media_por_corrida": media_de(fp)[0], "fp_de": media_de(fp)[1],
            "latencia_media_h": media_de([f["latencia_media_h"] for f in g])[0],
            "exactitud_polaridad_flujo": media_de([f["exactitud_polaridad_flujo"] for f in g])[0],
        }

    def agregado(filtro):
        g = [f for f in esc if filtro(f)]
        inc = sum(f["incidentes_relevantes"] for f in g)
        det = sum(f["detectados_24h"] for f in g)
        alertas = sum(f["alertas_total"] for f in g)
        fps = sum(f["alertas_fp"] for f in g)
        rep = sum(f["reportes_a_tiempo"] for f in g)
        sem = sum(f["semanas_cerradas"] for f in g)
        por_corrida_det = [f["detectados_24h"] / f["incidentes_relevantes"] for f in g if f["incidentes_relevantes"]]
        por_corrida_fp = [f["alertas_fp"] / f["alertas_total"] for f in g if f["alertas_total"]]
        return {"incidentes": inc, "detectados_24h": det, "tasa_deteccion": det / inc if inc else None,
                "deteccion_de_por_corrida": media_de(por_corrida_det)[1],
                "alertas": alertas, "fp": fps, "tasa_fp": fps / alertas if alertas else 0.0,
                "fp_de_por_corrida": media_de(por_corrida_fp)[1],
                "reportes_a_tiempo": rep, "semanas": sem, "tasa_reportes": rep / sem,
                "latencia_reporte_max_h": max(f["latencia_reporte_max_h"] for f in g),
                "corridas": len(g)}

    r["agregado_todos"] = agregado(lambda f: True)
    r["agregado_sin_fallas_esperadas"] = agregado(lambda f: f["tipo"] != "falla")
    a = r["agregado_todos"]
    holdout = r["m1"]["C03"]
    r["veredicto"] = {
        "M1": holdout["cumple"],
        "M2": a["tasa_deteccion"] >= U["M2_deteccion_24h"],
        "M3": a["tasa_reportes"] >= U["M3_reportes_a_tiempo"],
        "M4": a["tasa_fp"] < U["M4_falsos_positivos_max"],
    }
    return r


def pct(x, d=None):
    if x is None:
        return "—"
    return f"{x:.1%}" + (f" ± {d:.1%}" if d is not None else "")


def tabla_markdown(r):
    a, U = r["agregado_todos"], r["umbrales"]
    c3 = r["m1"]["C03"]
    v = r["veredicto"]
    si = lambda b: "Sí" if b else "No"
    lineas = [
        "| Medida de desempeño | Fórmula | Umbral | Casos ejecutados | Resultado obtenido | ¿Cumple? | Evidencia |",
        "|---|---|---|---|---|---|---|",
        f"| M1 Exactitud de clasificación | aciertos / reseñas evaluadas (polaridad y tema por separado) | "
        f"≥ {U['M1_exactitud_polaridad']:.0%} en ambas | 11 casos × 5 reentrenamientos | Control C03: polaridad "
        f"{pct(c3['polaridad_media'], c3['polaridad_de'])}, tema {pct(c3['tema_media'], c3['tema_de'])} | "
        f"{si(v['M1'])} | m1_clasificacion.csv |",
        f"| M2 Detección de cambios en 24 h | incidentes relevantes alertados ≤ 24 h tras el cierre / incidentes "
        f"relevantes | ≥ {U['M2_deteccion_24h']:.0%} | 12 escenarios × 5 semillas ({a['corridas']} corridas, "
        f"{a['incidentes']} incidentes) | {pct(a['tasa_deteccion'])} ({a['detectados_24h']}/{a['incidentes']}) | "
        f"{si(v['M2'])} | escenarios.csv, corridas/*/log_ejecucion.jsonl |",
        f"| M3 Reporte semanal a tiempo | reportes entregados ≤ 24 h tras el cierre / semanas cerradas | "
        f"= {U['M3_reportes_a_tiempo']:.0%} | 12 escenarios × 5 semillas ({a['semanas']} semanas) | "
        f"{pct(a['tasa_reportes'])} ({a['reportes_a_tiempo']}/{a['semanas']}); máx. {a['latencia_reporte_max_h']:.0f} h"
        f" | {si(v['M3'])} | corridas/*/reportes/ |",
        f"| M4 Falsos positivos de alerta | alertas sin incidente relevante / alertas enviadas | "
        f"< {U['M4_falsos_positivos_max']:.0%} | 12 escenarios × 5 semillas ({a['alertas']} alertas) | "
        f"{pct(a['tasa_fp'])} ({a['fp']}/{a['alertas']}) | {si(v['M4'])} | corridas/*/bandeja_salida.jsonl |",
    ]
    lineas += ["", "## M1 por caso (media ± desviación estándar en 5 reentrenamientos)", "",
               "| Caso | Descripción | Tipo | n | Polaridad | Tema | Rechazo | ¿Cumple? |", "|---|---|---|---|---|---|---|---|"]
    for cid, c in r["m1"].items():
        lineas.append(f"| {cid} | {c['descripcion']} | {c['tipo']} | {c['n']} | {pct(c['polaridad_media'], c['polaridad_de'])}"
                      f" | {pct(c['tema_media'], c['tema_de'])} | {pct(c['rechazo_media'], c['rechazo_de'])} | {si(c['cumple'])} |")
    lineas += ["", "## Escenarios del agente (5 semillas cada uno)", "",
               "| Escenario | Tipo | Detección ≤ 24 h | Detectadas tarde | Reportes a tiempo | Alertas | Falsos positivos |"
               " Latencia media alerta |", "|---|---|---|---|---|---|---|---|"]
    for eid, e in r["escenarios"].items():
        lat = f"{e['latencia_media_h']:.0f} h" if e["latencia_media_h"] is not None else "—"
        lineas.append(f"| {e['nombre']} | {e['tipo']} | {pct(e['deteccion_media'], e['deteccion_de'])} | "
                      f"{e['detectados_tarde_total']} | {pct(e['reportes_media'], e['reportes_de'])} | {e['alertas_total']} |"
                      f" {e['fp_total']} ({e['fp_media_por_corrida']:.1f} ± {e['fp_de']:.1f} por corrida) | {lat} |")
    b = r["agregado_sin_fallas_esperadas"]
    lineas += ["", f"Sin los escenarios de falla esperada: detección {pct(b['tasa_deteccion'])} "
               f"({b['detectados_24h']}/{b['incidentes']}), falsos positivos {pct(b['tasa_fp'])} ({b['fp']}/{b['alertas']})."]
    return "\n".join(lineas)


def guardar_csv(ruta, filas):
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true", help="una sola repetición")
    args = ap.parse_args()
    global SALIDA
    semillas = UMBRALES["semillas"][:1] if args.rapido else UMBRALES["semillas"]
    if args.rapido:  # no pisar los resultados oficiales de la corrida completa
        SALIDA = RAIZ / "salidas" / "pruebas_rapido"
    SALIDA.mkdir(parents=True, exist_ok=True)
    print(f"Umbrales fijados el {UMBRALES['fijados_el']}. Repeticiones: {len(semillas)}")
    print("Prueba M1 (clasificación)…")
    m1 = prueba_m1(semillas)
    guardar_csv(SALIDA / "m1_clasificacion.csv", m1)
    print("Pruebas M2–M4 (escenarios del agente)…")
    modelo = ClasificadorSentimiento.cargar()
    esc = prueba_escenarios(semillas, modelo)
    guardar_csv(SALIDA / "escenarios.csv", esc)
    r = resumir(m1, esc)
    (SALIDA / "resumen.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    tabla = tabla_markdown(r)
    if args.rapido:
        aviso = ("> **MODO RÁPIDO (1 repetición, semilla 11).** Resultado de demostración: no es el resultado oficial. "
                 "El oficial (5 repeticiones) está en salidas/pruebas/.\n\n")
        tabla = aviso + tabla.replace("11 casos × 5 reentrenamientos", "11 casos × 1 reentrenamiento").replace("12 escenarios × 5 semillas", "12 escenarios × 1 semilla").replace("en 5 reentrenamientos", "en 1 reentrenamiento").replace("(5 semillas cada uno)", "(1 semilla cada uno)")
    (SALIDA / "tabla_resultados.md").write_text(tabla, encoding="utf-8")
    print("\n" + tabla)
    print("\nVeredicto:", r["veredicto"])


if __name__ == "__main__":
    main()
