"""Lectura de lote y fecha de vencimiento en la foto de un empaque.

Se le pasa la imagen a un modelo de visión por OpenRouter (por defecto
qwen/qwen3-vl-plus). El resultado es solo una sugerencia: el frontend lo usa
para llenar el formulario y el usuario lo revisa antes de guardar.

Viene del proyecto ModelScanProducts (providers/openrouter.py, common.py y el
prompt de main.py), adaptado para recibir la foto que manda el frontend en
lugar de leer una carpeta de fotos.
"""

import base64
import calendar
import json
import logging
import re
from datetime import date
from typing import Literal

from openai import APIStatusError, APITimeoutError, AsyncOpenAI, OpenAIError
from pydantic import BaseModel, ValidationError, field_validator

from app.config import get_settings
from app.exceptions import LecturaFallida, LecturaNoConfigurada, LecturaSaturada
from app.schemas.tracking import ExtraccionFoto

logger = logging.getLogger(__name__)

# Esquema que se le pide al modelo. OpenRouter no garantiza json_schema
# estricto para todos los modelos, así que se fuerza JSON con json_object y
# el esquema va como instrucción en el system prompt.
ESQUEMA = {
    "type": "object",
    "properties": {
        "lote": {"type": ["string", "null"]},
        "fecha_cruda": {"type": ["string", "null"]},
        "venc_dia": {"type": ["integer", "null"]},
        "venc_mes": {"type": ["integer", "null"]},
        "venc_anio": {"type": ["integer", "null"]},
        "venc_precision": {"type": "string", "enum": ["dia", "mes", "nulo"]},
        "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
        "notas": {"type": ["string", "null"]},
    },
    "required": [
        "lote",
        "fecha_cruda",
        "venc_dia",
        "venc_mes",
        "venc_anio",
        "venc_precision",
        "confianza",
        "notas",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "Respondes UNICAMENTE con un objeto JSON que cumpla exactamente este "
    "JSON Schema, sin texto adicional ni bloques de codigo:\n"
    + json.dumps(ESQUEMA, ensure_ascii=False)
)

PROMPT = """Esta es la impresion (codificado / inkjet) de un empaque de alimentos.
Extrae el numero de LOTE y la FECHA DE VENCIMIENTO.

IDENTIFICAR LOS CAMPOS
- El vencimiento viene despues de VEN, VENC, VENCE, V. o CAD.
- El lote esta marcado por L, L., L:, LOTE o LOT.
- Si no hay marcador, el codigo alfanumerico que no sea una fecha es el lote.
- La L de unidades o palabras (500ML, CL, KL, NEUTRAL) no es marcador de lote.

LOTE: COPIA LITERAL, no lo limpies
- Devuelvelo EXACTAMENTE como esta impreso, incluyendo el marcador, las etiquetas,
  los espacios y los separadores. De limpiarlo se encarga otro proceso.
  Ej: "L61050467"         -> devuelve "L61050467"
  Ej: "L VEN 01 SEP 2026" -> devuelve "L VEN 01 SEP 2026"
  Ej: "LOTE 04-L1 0107"   -> devuelve "LOTE 04-L1 0107"
- Los dos puntos DENTRO del codigo (ej: L15616:34GMMP) son parte del lote: conservalos.
- Es valido que el lote sea identico a la fecha impresa (ej: "L VEN 01 SEP 2026",
  donde una sola impresion sirve para los dos campos). No lo descartes, no devuelvas
  null, y no inventes un lote distinto.

FECHA: descomponer, NO calcular
- "fecha_cruda": los caracteres tal como aparecen, sin interpretar.
- Descompon la fecha en venc_dia / venc_mes / venc_anio (numeros).
- Anio de 2 digitos -> 20XX. Si el dia y el mes son ambiguos, asume DD/MM
  (formato latinoamericano).
- Meses en letras: ENE=1 FEB=2 MAR=3 ABR=4 MAY=5 JUN=6 JUL=7 AGO=8 SEP=9
  OCT=10 NOV=11 DIC=12.
- Si el empaque trae dia, mes y anio -> venc_precision = "dia".
- Si el empaque SOLO trae mes y anio (ej: 05/2027, DIC/26, SEP 2026) ->
  venc_precision = "mes" y venc_dia = null. NO completes el dia:
  de eso se encarga otro proceso.
- Si no hay fecha legible -> venc_precision = "nulo" y los tres campos en null.

CUANDO NO LEES ALGO
- Devuelve null en ese campo y explica en "notas". NO adivines ni completes
  caracteres que no ves. Un null es preferible a un valor inventado.

CONFIANZA - usa estos disparadores, no tu impresion general
- "baja" OBLIGATORIO si: el codigo toca o se sale del borde de la imagen,
  hay caracteres tapados por brillo/pliegue/relieve, o dudas entre dos
  lecturas que dan valores distintos.
- "media" si: el valor es correcto pero algun caracter admite otra lectura
  (0/O, 1/I/L, 5/S, 8/B, 2/Z), o los separadores son ambiguos.
- "alta" solo si podrias transcribir el codigo de memoria sin volver a mirar."""


class _RespuestaModelo(BaseModel):
    """Lo que devuelve el modelo, aceptando pequeñas desviaciones del esquema."""

    lote: str | None = None
    fecha_cruda: str | None = None
    venc_dia: int | None = None
    venc_mes: int | None = None
    venc_anio: int | None = None
    venc_precision: Literal["dia", "mes", "nulo"] = "nulo"
    confianza: Literal["alta", "media", "baja"] = "baja"
    notas: str | None = None

    @field_validator("lote", "fecha_cruda", "notas", mode="before")
    @classmethod
    def _texto_vacio_es_null(cls, valor):
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor.strip() if isinstance(valor, str) else valor

    @field_validator("venc_precision", mode="before")
    @classmethod
    def _precision(cls, valor):
        valor = str(valor or "nulo").strip().lower()
        return valor if valor in ("dia", "mes") else "nulo"

    @field_validator("confianza", mode="before")
    @classmethod
    def _confianza(cls, valor):
        # Ante un valor raro no se le da el beneficio de la duda.
        valor = str(valor or "").strip().lower()
        return valor if valor in ("alta", "media") else "baja"


def armar_fecha(datos: _RespuestaModelo) -> date | None:
    """Convierte día/mes/año en una fecha para el formulario.

    Con precisión "mes" se usa el último día del mes, que es como se
    interpreta un vencimiento impreso solo con mes y año. Una fecha imposible
    (ej. 31/02) devuelve None.
    """
    if datos.venc_precision == "nulo" or datos.venc_mes is None or datos.venc_anio is None:
        return None
    anio = datos.venc_anio + 2000 if datos.venc_anio < 100 else datos.venc_anio
    try:
        if datos.venc_precision == "mes":
            return date(anio, datos.venc_mes, calendar.monthrange(anio, datos.venc_mes)[1])
        if datos.venc_dia is None:
            return None
        return date(anio, datos.venc_mes, datos.venc_dia)
    except ValueError:
        return None


def describir_error(error: Exception) -> str:
    """Causa corta y legible del fallo. Nunca incluye la clave ni la imagen."""
    if isinstance(error, APITimeoutError):
        return "OpenRouter no respondió a tiempo"
    if isinstance(error, APIStatusError):
        # OpenRouter manda {"message": ...} o {"error": {"message": ...}}
        cuerpo = error.body if isinstance(error.body, dict) else {}
        detalle = cuerpo.get("error") if isinstance(cuerpo.get("error"), dict) else cuerpo
        mensaje = detalle.get("message")
        return f"OpenRouter respondió {error.status_code}: {mensaje or error.message}"[:300]
    if isinstance(error, OpenAIError):
        return f"No se pudo conectar con OpenRouter ({type(error).__name__})"
    return f"La respuesta del modelo no tiene el formato esperado ({type(error).__name__}: {error})"[:300]


def _leer_json(texto: str | None) -> dict:
    """El JSON de la respuesta; tolera que venga envuelto en ```json ... ```."""
    if not texto:
        raise ValueError("respuesta vacía")
    coincidencia = re.search(r"\{.*\}", texto, re.DOTALL)
    return json.loads(coincidencia.group(0) if coincidencia else texto)


async def extraer_datos(contenido: bytes, tipo: str) -> ExtraccionFoto:
    """Lee lote y vencimiento de la foto. Lanza LecturaNoConfigurada o LecturaFallida."""
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise LecturaNoConfigurada()

    data_url = f"data:{tipo};base64,{base64.standard_b64encode(contenido).decode('ascii')}"
    try:
        async with AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            timeout=settings.openrouter_timeout_segundos,
            max_retries=1,
        ) as cliente:
            respuesta = await cliente.chat.completions.create(
                model=settings.openrouter_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PROMPT},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ],
                response_format={"type": "json_object"},
            )
        datos = _RespuestaModelo.model_validate(_leer_json(respuesta.choices[0].message.content))
    except (OpenAIError, ValueError, ValidationError, IndexError, AttributeError) as error:
        causa = describir_error(error)
        logger.warning("Falló la lectura de la foto (modelo %s): %s", settings.openrouter_model, causa)
        # 429: OpenRouter (o el proveedor del modelo) está saturado; reintentar luego sirve.
        if isinstance(error, APIStatusError) and error.status_code == 429:
            raise LecturaSaturada(settings.openrouter_model) from error
        raise LecturaFallida(causa, settings.openrouter_model) from error

    return ExtraccionFoto(
        lote=datos.lote,
        fecha_vencimiento=armar_fecha(datos),
        fecha_cruda=datos.fecha_cruda,
        venc_precision=datos.venc_precision,
        confianza=datos.confianza,
        notas=datos.notas,
    )
