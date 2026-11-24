"""Graba tres conversaciones reales para el modo demo de la API.

Requiere configuración del proveedor en .env. No guarda nada si una charla
falla, no usa herramientas o no termina con una respuesta verificada.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from reviewpulse.api.estado import EstadoAPI
from reviewpulse.agente.bucle import resolver
from reviewpulse.config import cargar_ajustes
from reviewpulse.llm.cliente import ClienteOpenAI

RAIZ = Path(__file__).resolve().parents[1]
TRAZAS = RAIZ / "data" / "trazas_demo"
CASOS = (
    {
        "id": "chat-conteo-semana-08",
        "archivo": "cierre-semana-00.json",
        "pregunta": "¿Cuántas reseñas hubo en la semana 8?",
        "disparadores": [
            "cuantas resenas semana 8", "conteo de resenas semana 8",
            "conteo semana 8",
        ],
    },
    {
        "id": "chat-servicio-semana-08",
        "archivo": "alerta-servicio-semana-08.json",
        "pregunta": "¿El servicio empeoró en la semana 8?",
        "disparadores": ["servicio semana 8", "empeoro servicio semana 8"],
    },
    {
        "id": "chat-consulta-semana-40",
        "archivo": "cierre-semana-13.json",
        "pregunta": "¿Cuántas reseñas hubo en la semana 40?",
        "disparadores": ["resenas semana 40", "consulta semana 40", "semana 40"],
    },
)


def _grabar(estado: EstadoAPI, caso: dict) -> dict:
    solicitudes_antes = estado.proveedor.solicitudes
    resultado = resolver(
        caso["pregunta"], estado.llm, estado.contexto(), max_pasos=2
    )
    solicitudes = estado.proveedor.solicitudes - solicitudes_antes
    if solicitudes > 2:
        raise RuntimeError("Se excedió el máximo de dos solicitudes para este chat.")
    eventos = [
        {
            "fase": "PERCEPCION",
            "evento": "tarea_recibida",
            "pregunta": caso["pregunta"],
        },
        *(
            evento for evento in resultado.eventos
            if evento.get("evento") != "tarea_recibida"
        ),
    ]
    herramientas = list(dict.fromkeys(
        evento["herramienta"] for evento in eventos
        if evento.get("evento") == "herramienta"
    ))
    if not resultado.ok or not herramientas:
        raise RuntimeError(
            f"No se pudo grabar {caso['id']}: la conversación no terminó "
            "correctamente con al menos una herramienta."
        )
    final = next(
        (e for e in reversed(eventos) if e.get("evento") == "respuesta_final"),
        None,
    )
    if final is None or final.get("verificada") is not True:
        raise RuntimeError(f"La respuesta de {caso['id']} no quedó verificada.")

    traza = {
        "id": caso["id"],
        "origen": {
            "tipo": "conversacion_real_agente",
            "escenario": "E03",
            "semilla": 11,
            "modelo": estado.ajustes.llm_model,
            "solicitudes_proveedor": solicitudes,
            "grabada_en": datetime.now(timezone.utc).isoformat(),
        },
        "pregunta": caso["pregunta"],
        "disparadores": caso["disparadores"],
        "herramientas": herramientas,
        "eventos": eventos,
        "respuesta_final": resultado.texto,
    }
    # Evita persistir credenciales si aparecieran accidentalmente en la salida.
    seguro = estado.texto_seguro(json.dumps(traza, ensure_ascii=False))
    return json.loads(seguro)


def main() -> int:
    ajustes = cargar_ajustes()
    if not all((
        ajustes.llm_base_url,
        ajustes.llm_api_key,
        ajustes.llm_model,
        ajustes.llm_juez_model,
        ajustes.app_codigo_acceso,
        ajustes.llm_tope_tokens_dia,
    )):
        raise SystemExit(
            "Falta una de las seis variables requeridas en .env; "
            "no se realizó ninguna llamada."
        )

    TRAZAS.mkdir(parents=True, exist_ok=True)
    anteriores = os.environ.get("REVIEWPULSE_DB_PATH")
    try:
        with tempfile.TemporaryDirectory(prefix="reviewpulse-trazas-demo-") as temporal:
            os.environ["REVIEWPULSE_DB_PATH"] = str(Path(temporal) / "demo.sqlite3")
            cliente = ClienteOpenAI(ajustes, max_intentos=1)
            estado = EstadoAPI(ajustes, cliente)
            try:
                grabadas = [_grabar(estado, caso) for caso in CASOS]
                if cliente.solicitudes > 6:
                    raise RuntimeError("Se excedió el límite de seis solicitudes proveedor.")
                solicitudes_usadas = cliente.solicitudes
            finally:
                estado.cerrar()
    finally:
        if anteriores is None:
            os.environ.pop("REVIEWPULSE_DB_PATH", None)
        else:
            os.environ["REVIEWPULSE_DB_PATH"] = anteriores

    # Publica el conjunto completo solo después de capturar y validar las tres.
    temporales: list[tuple[Path, Path]] = []
    try:
        for caso, traza in zip(CASOS, grabadas):
            destino = TRAZAS / caso["archivo"]
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=TRAZAS, delete=False
            ) as archivo:
                json.dump(traza, archivo, ensure_ascii=False, indent=2)
                archivo.write("\n")
                temporales.append((Path(archivo.name), destino))
        for temporal, destino in temporales:
            temporal.replace(destino)
    finally:
        for temporal, _destino in temporales:
            temporal.unlink(missing_ok=True)

    print(f"Se grabaron {len(grabadas)} trazas reales en {TRAZAS}.")
    print(f"Solicitudes al proveedor utilizadas: {solicitudes_usadas}/6.")
    print(f"Tokens utilizados: {estado._tokens_dia}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
