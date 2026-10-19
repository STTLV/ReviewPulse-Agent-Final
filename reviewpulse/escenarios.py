"""Escenarios de prueba del entorno simulado (normales, límite y de falla esperada).

Cada incidente "relevante" es un deterioro real que el agente DEBE alertar;
un incidente "leve" es una variación que NO debe disparar alerta.
"""
from datetime import timedelta

from .entorno import Caida, Escenario, Incidente, inicio_semana


def _cierre(semana: int):
    return inicio_semana(semana + 1)


ESCENARIOS = {
    "E01": Escenario("E01 Operación estable", "14 semanas sin incidentes; volumen y tono habituales.", "normal"),
    "E02": Escenario("E02 Incidente de limpieza", "Semana 9: problema de aseo; 65 % de reseñas de limpieza negativas.",
                     "normal", incidentes=[Incidente(9, "limpieza", "relevante", 0.65, 2.5)]),
    "E03": Escenario("E03 Dos incidentes", "Semana 8 falla de servicio; semana 11 cobros indebidos (precio).",
                     "normal", incidentes=[Incidente(8, "servicio", "relevante", 0.60, 2.2),
                                           Incidente(11, "precio", "relevante", 0.65, 2.5)]),
    "E04": Escenario("E04 Temporada alta", "Semanas 8 a 11 con 2,5 veces más reseñas pero el mismo tono.", "limite",
                     multiplicador_volumen={8: 2.5, 9: 2.5, 10: 2.5, 11: 2.5}),
    "E05": Escenario("E05 Incidente moderado", "Semana 9: ruido de una obra; 50 % negativas en ubicación.",
                     "limite", incidentes=[Incidente(9, "ubicacion", "relevante", 0.50, 1.8)]),
    "E06": Escenario("E06 Variación leve", "Semana 9: leve aumento de quejas de servicio (32 %), no debe alertar.",
                     "limite", incidentes=[Incidente(9, "servicio", "leve", 0.32, 1.2)]),
    "E07": Escenario("E07 Volumen bajo", "Solo 12 reseñas por semana; incidente de limpieza en semana 10.",
                     "limite", volumen_base=12, incidentes=[Incidente(10, "limpieza", "relevante", 0.70, 2.5)]),
    "E08": Escenario("E08 Ironía alta", "40 % de las reseñas negativas son irónicas; incidente de servicio sem. 9.",
                     "limite", prob_ironia=0.40, incidentes=[Incidente(9, "servicio", "relevante", 0.65, 2.5)]),
    "E09": Escenario("E09 Entradas inválidas", "15 % en otro idioma y 10 % vacías, HTML o sin fecha; incidente de "
                     "precio en semana 9.", "falla", prob_otro_idioma=0.15, prob_invalida=0.10,
                     incidentes=[Incidente(9, "precio", "relevante", 0.65, 2.5)]),
    "E10": Escenario("E10 TripAdvisor caído", "TripAdvisor no responde desde el domingo de la semana 8 hasta el "
                     "miércoles siguiente; incidente de limpieza en semana 8.", "falla",
                     incidentes=[Incidente(8, "limpieza", "relevante", 0.65, 2.5)],
                     caidas=[Caida("TripAdvisor", _cierre(8) - timedelta(hours=12), _cierre(8) + timedelta(days=2))]),
    "E11": Escenario("E11 Todas las plataformas caídas", "Ninguna plataforma responde durante toda la semana 9 y "
                     "36 h después; incidente de servicio en semana 9.", "falla",
                     incidentes=[Incidente(9, "servicio", "relevante", 0.65, 2.5)],
                     caidas=[Caida("todas", inicio_semana(9), _cierre(9) + timedelta(hours=36))]),
    "E12": Escenario("E12 Arranque en frío", "Incidente de precio en la semana 2, sin historial suficiente para "
                     "comparar.", "falla", incidentes=[Incidente(2, "precio", "relevante", 0.65, 2.5)]),
}
