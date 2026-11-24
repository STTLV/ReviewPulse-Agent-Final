"""Bucle ReAct determinista en la ejecución y flexible en la decisión LLM.

Solo el adaptador del LLM habla con el proveedor. Las acciones y las reglas de
seguridad permanecen en las herramientas de Tarea 5.
"""
from __future__ import annotations

import inspect
import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Callable

from ..herramientas.registro import Contexto, catalogo_openai, ejecutar
from ..llm.cliente import ClienteLLM, Uso
from .contexto import MemoriaSesion
from .prompts import PROMPT_SISTEMA
from .traza import Traza

_PATRON_NUMERO = re.compile(r"(?<![\w])[-+]?\d+(?:[.,]\d+)*(?:\s*%)?(?![\w])", re.UNICODE)
# Un ID alfanumerico con guiones no es una cantidad verificable.
_PATRON_ID_COMPUESTO = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)+(?![A-Za-z0-9_])"
)


@dataclass
class Resultado:
    ok: bool
    texto: str
    motivo: str
    pasos: int
    uso: Uso
    cifras_sin_respaldo: list[str]
    eventos: list[dict]


def extraer_cifras(texto: str) -> list[str]:
    """Extrae números con decimales, separadores de millares y porcentajes."""
    if not isinstance(texto, str):
        return []
    # T03 y T04 contienen IDs como T9-INY-01; su sufijo no es un total.
    sin_ids = _PATRON_ID_COMPUESTO.sub(lambda m: " " * len(m.group()), texto)
    return [m.group().strip() for m in _PATRON_NUMERO.finditer(sin_ids)]


def _numero(valor: str) -> Decimal | None:
    limpio = valor.strip().replace(" ", "").rstrip("%")
    if not limpio:
        return None
    # 1.234,56 o 1,234.56: el último separador determina decimales.
    if "," in limpio and "." in limpio:
        decimal = "," if limpio.rfind(",") > limpio.rfind(".") else "."
        millar = "." if decimal == "," else ","
        limpio = limpio.replace(millar, "").replace(decimal, ".")
    elif "," in limpio:
        partes = limpio.split(",")
        if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]) and len(partes[0]) <= 3 and partes[0] != "0":
            limpio = "".join(partes)
        else:
            limpio = limpio.replace(",", ".")
    elif "." in limpio:
        partes = limpio.split(".")
        if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]) and len(partes[0]) <= 3 and partes[0] != "0":
            limpio = "".join(partes)
    try:
        return Decimal(limpio)
    except InvalidOperation:
        return None


def _precision_de_cifra(cifra: str) -> Decimal:
    """Unidad del último decimal mostrado, sin confundir millares con decimales."""
    limpio = cifra.strip().replace(" ", "").rstrip("%")
    if "." in limpio and "," in limpio:
        sep = "," if limpio.rfind(",") > limpio.rfind(".") else "."
        return Decimal(1).scaleb(-len(limpio.rsplit(sep, 1)[1]))
    for sep in (",", "."):
        if sep not in limpio:
            continue
        partes = limpio.lstrip("+-").split(sep)
        # Igual que _numero: grupos de tres son separadores de millares.
        if (len(partes) > 1 and all(len(p) == 3 for p in partes[1:])
                and len(partes[0]) <= 3 and partes[0] != "0"):
            return Decimal("1")
        return Decimal(1).scaleb(-len(partes[-1]))
    return Decimal("1")


def _equivale_redondeado(valor: Decimal, respaldo: Decimal, precision: Decimal) -> bool:
    # Un número fuera de la precisión decimal disponible no se verifica.
    # No debe abortar el bucle ReAct ni convertir la cifra en respaldada.
    try:
        return respaldo.quantize(precision, rounding=ROUND_HALF_UP) == valor
    except (InvalidOperation, ValueError, OverflowError):
        return False


def cifras_sin_respaldo(texto: str, observaciones: list[str]) -> list[str]:
    """Comprueba las cifras contra los números aportados por usuario/herramientas.

    Una proporción 0.7 respalda el porcentaje 70 %. No se concede respaldo por
    números derivados solo de respuestas anteriores del LLM.
    """
    respaldos = []
    for obs in observaciones:
        for cifra in extraer_cifras(str(obs)):
            numero = _numero(cifra)
            if numero is not None:
                respaldos.append(numero)
    sin_respaldo: list[str] = []
    for cifra in extraer_cifras(texto):
        valor = _numero(cifra)
        es_porcentaje = cifra.rstrip().endswith("%")
        if valor is None:
            continue
        precision = _precision_de_cifra(cifra)
        if not es_porcentaje and precision == Decimal("1"):
            # Una cantidad entera no puede inventarse mediante redondeo:
            # ni 0.1 respalda "0 quejas", ni 5.12 respalda "5 quejas".
            valido = valor in respaldos
        else:
            # Se permite redondear solo decimales o porcentajes explícitos.
            valido = any(_equivale_redondeado(valor, numero, precision) for numero in respaldos)
        if es_porcentaje and not valido:
            valido = any(
                _equivale_redondeado(valor, numero * 100, precision)
                for numero in respaldos if 0 <= numero <= 1
            )
        if not valido and cifra not in sin_respaldo:
            sin_respaldo.append(cifra)
    return sin_respaldo


def _argumentos_visibles(crudos: str) -> dict:
    """No registra contenido de reseñas ni claves ni texto libre de usuarios."""
    try:
        args = json.loads(crudos)
    except (TypeError, ValueError):
        return {"json_valido": False, "longitud": len(str(crudos))}
    if not isinstance(args, dict):
        return {"json_valido": True, "tipo": type(args).__name__}
    seguros = {}
    sensibles = ("key", "clave", "secret", "token", "password", "authorization", "texto", "justificacion")
    for clave, valor in args.items():
        if any(s in clave.lower() for s in sensibles):
            seguros[clave] = "[omitido]"
        elif isinstance(valor, (str, float, int, bool)) or valor is None:
            seguros[clave] = valor if not isinstance(valor, str) else valor[:80]
        else:
            seguros[clave] = "[estructura]"
    return seguros


def _resumen_observacion(datos: dict) -> dict:
    """Registra si la acción ocurrió sin replicar reseñas ni rutas privadas."""
    resumen = {"ok": datos.get("ok")}
    if "error" in datos:
        resumen["error"] = datos["error"]
    valor = datos.get("datos")
    if isinstance(valor, dict):
        resumen["campos"] = list(valor)[:20]
        for clave in ("total", "semana", "emitida", "alarma"):
            if clave in valor and isinstance(valor[clave], (int, float, bool)):
                resumen[clave] = valor[clave]
    elif isinstance(valor, list):
        resumen["elementos"] = len(valor)
    return resumen


def resolver(
    tarea: str,
    llm: ClienteLLM,
    ctx: Contexto,
    memoria: MemoriaSesion | None = None,
    traza: Traza | None = None,
    max_pasos: int = 8,
    max_tokens: int = 40000,
    al_evento: Callable | None = None,
) -> Resultado:
    """Resuelve una tarea: percepción, decisión, herramienta y observación.

    Reintenta una única vez una respuesta con cifras inventadas. Tanto fallos
    de proveedor como errores de herramientas se convierten en resultados.
    """
    sesion = memoria if memoria is not None else MemoriaSesion(PROMPT_SISTEMA)
    registro = traza if traza is not None else Traza()
    uso = Uso(0, 0)
    pasos = 0
    correccion_pedida = False
    pendientes: list[str] = []
    observaciones = [tarea]
    observaciones_herramientas: list[str] = []

    def registrar(fase: str, evento: str, **datos):
        item = registro.evento(fase, evento, **datos)
        if al_evento is not None:
            try:
                al_evento(item)
            except Exception:
                # Un consumidor SSE desconectado no bloquea la tarea.
                registro.evento("SISTEMA", "consumidor_desconectado")
        return item

    def salida(ok: bool, texto: str, motivo: str, sin_respaldo: list[str] | None = None):
        return Resultado(ok, texto, motivo, pasos, uso, list(sin_respaldo or []), list(registro.eventos))

    if not isinstance(tarea, str) or not tarea.strip():
        return salida(False, "No hay una tarea que ejecutar.", "tarea_invalida")
    if max_pasos < 1:
        return salida(False, "Se alcanzó el límite de pasos.", "limite_de_pasos")
    if max_tokens < 1:
        return salida(False, "Se alcanzó el límite de tokens.", "limite_de_tokens")

    sesion.agregar({"role": "user", "content": tarea})
    registrar("PERCEPCION", "tarea_recibida", longitud=len(tarea))
    catalogo = catalogo_openai()
    for paso in range(1, max_pasos + 1):
        pasos = paso
        inicio = time.monotonic()
        try:
            respuesta = llm.chat(sesion.mensajes, herramientas=catalogo)
        except Exception:
            registrar("DECISION", "fallo_proveedor", paso=paso, segundos=round(time.monotonic()-inicio, 4))
            return salida(False, "El proveedor no pudo completar la tarea.", "proveedor")

        gasto = respuesta.uso or Uso(0, 0)
        uso.entrada += max(0, int(gasto.entrada or 0))
        uso.salida += max(0, int(gasto.salida or 0))
        registrar("DECISION", "respuesta_llm", paso=paso, ok=respuesta.ok,
                  tokens_entrada=gasto.entrada, tokens_salida=gasto.salida,
                  segundos=round(time.monotonic()-inicio, 4),
                  llamadas=len(respuesta.llamadas or []))
        if uso.entrada + uso.salida > max_tokens:
            registrar("SISTEMA", "limite_tokens", total=uso.entrada + uso.salida)
            return salida(False, "Se alcanzó el límite de tokens.", "limite_de_tokens")
        if not respuesta.ok:
            codigo = respuesta.error if respuesta.error in {"proveedor", "autenticacion", "no_configurado"} else "proveedor"
            registrar("DECISION", "error_llm", motivo=codigo)
            return salida(False, "El proveedor no pudo completar la tarea.", codigo)

        llamadas = respuesta.llamadas or []
        mensaje = respuesta.mensaje_asistente
        if not isinstance(mensaje, dict):
            mensaje = {"role": "assistant", "content": respuesta.texto}
            if llamadas:
                mensaje["tool_calls"] = [
                    {"id": llamada.id or f"paso-{paso}-llamada-{i}", "type": "function",
                     "function": {"name": llamada.nombre, "arguments": llamada.argumentos_crudos}}
                    for i, llamada in enumerate(llamadas)
                ]
        sesion.agregar(mensaje)
        if llamadas:
            for i, llamada in enumerate(llamadas):
                identificador = llamada.id or f"paso-{paso}-llamada-{i}"
                inicio_accion = time.monotonic()
                resultado = ejecutar(llamada.nombre, llamada.argumentos_crudos, ctx)
                observacion = json.dumps(resultado, ensure_ascii=False, default=str)
                observaciones.append(observacion)
                observaciones_herramientas.append(observacion)
                sesion.agregar({"role": "tool", "tool_call_id": identificador,
                               "name": llamada.nombre, "content": observacion})
                registrar("ACCION", "herramienta", paso=paso, herramienta=llamada.nombre,
                          argumentos=_argumentos_visibles(llamada.argumentos_crudos),
                          resultado=_resumen_observacion(resultado),
                          segundos=round(time.monotonic()-inicio_accion, 4))
            registrar("OBSERVACION", "herramientas_observadas", paso=paso, cantidad=len(llamadas))
            continue

        texto = str(respuesta.texto or "")
        # Indicador T9/T13: cantidades numéricas de la respuesta justificadas
        # por OBSERVACIONES DE HERRAMIENTAS, no por el texto del usuario.
        # Se registran sólo conteos, nunca datos originales sensibles.
        # "semana 8" es el periodo solicitado, no una afirmación cuantitativa.
        texto_medido = re.sub(r"(?i)\bsemanas?\s+(?:n[úu]mero\s+)?\d+\b", "", texto)
        cifras_finales = extraer_cifras(texto_medido)
        no_trazables = cifras_sin_respaldo(texto_medido, observaciones_herramientas)
        trazabilidad_datos = {
            "cifras_evaluadas": len(cifras_finales),
            "cifras_respaldadas": sum(c not in no_trazables for c in cifras_finales),
        }
        pendientes = cifras_sin_respaldo(texto, observaciones)
        if not pendientes:
            registrar("ACCION", "respuesta_final", paso=paso, verificada=True, **trazabilidad_datos)
            return salida(True, texto, "completado")
        if not correccion_pedida and paso < max_pasos:
            correccion_pedida = True
            registrar("VERIFICACION", "cifras_sin_respaldo", paso=paso, cifras=pendientes)
            sesion.agregar({"role": "user", "content": (
                "Corrige tu respuesta una sola vez: hay cifras sin respaldo en las "
                "observaciones de herramientas o en la pregunta. Omite esas cifras "
                "o consulta una herramienta. No inventes valores."
            )})
            continue
        texto = texto.rstrip() + "\n[Advertencia: cifra sin respaldo: " + ", ".join(pendientes) + "]"
        registrar("ACCION", "respuesta_final", paso=paso, verificada=False, cifras=pendientes, **trazabilidad_datos)
        return salida(True, texto, "cifra_sin_respaldo", pendientes)

    if pendientes:
        texto = "La respuesta quedó sin verificar. [Advertencia: cifra sin respaldo: " + ", ".join(pendientes) + "]"
        return salida(False, texto, "limite_de_pasos", pendientes)
    registrar("SISTEMA", "limite_pasos", total=max_pasos)
    return salida(False, "Se alcanzó el límite de pasos.", "limite_de_pasos")


class ManejadorAgente:
    """Adaptador al contrato ciclo.cierre.Manejador.

    La fábrica recibe ``ahora: datetime`` y devuelve un Contexto de Tarea 5.
    El ciclo determinista sigue siendo responsable del fallback.
    """

    def __init__(self, llm: ClienteLLM, fabrica_contexto: Callable):
        self.llm = llm
        self.fabrica_contexto = fabrica_contexto

    def _contexto(self, ahora):
        """Admite fábricas con fecha o sin argumentos sin ocultar fallos internos."""
        try:
            inspect.signature(self.fabrica_contexto).bind(ahora)
        except TypeError:
            return self.fabrica_contexto()
        return self.fabrica_contexto(ahora)

    def al_alarmar(self, alarma, ahora) -> None:
        ctx = self._contexto(ahora)
        tarea = f"ALARMA semana={alarma.semana} tema={alarma.tema}"
        r = resolver(tarea, self.llm, ctx)
        if not r.ok:
            raise RuntimeError("El agente no pudo gestionar la alarma.")
        alertas = ctx.repo.alertas()
        if not any(a.get("semana") == alarma.semana and a.get("tema") == alarma.tema for a in alertas):
            # CierreSemanal invocará el fallback determinista.
            raise RuntimeError("El agente no emitió la alerta prevista.")

    def al_cerrar(self, semana: int, ahora, incompleto: bool) -> bool:
        ctx = self._contexto(ahora)
        if ctx.sesion.semana_en_cierre is not None:
            raise RuntimeError("Ya existe un cierre activo en la sesión.")
        ctx.sesion.incompleto = bool(incompleto)
        # Autoriza el cierre el ciclo de ingesta, no las palabras del LLM.
        ctx.sesion.semana_en_cierre = semana
        try:
            r = resolver(f"CIERRE semana={semana} incompleto={int(incompleto)}", self.llm, ctx)
            if not r.ok:
                return False
            return any(informe.get("semana") == semana for informe in ctx.repo.reportes())
        finally:
            # La autorización y la marca incompleta pertenecen solo al cierre
            # activo. No deben contaminar un segundo reporte con el mismo ctx.
            ctx.sesion.semana_en_cierre = None
            ctx.sesion.incompleto = False
