"""Lectura de lote y vencimiento con OpenRouter. El cliente de OpenAI se
reemplaza por uno falso: ningún test llama a la API real."""

import json
from datetime import date
from types import SimpleNamespace

import pytest
from openai import APITimeoutError

from app.config import get_settings
from app.services import extraccion

URL = "/trackings/photo"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200

RESPUESTA_COMPLETA = {
    "lote": "L61050467",
    "fecha_cruda": "VEN 15/03/27",
    "venc_dia": 15,
    "venc_mes": 3,
    "venc_anio": 2027,
    "venc_precision": "dia",
    "confianza": "alta",
    "notas": None,
}


class ClienteFalso:
    """Imita AsyncOpenAI: guarda lo que se le pidió y devuelve `contenido`."""

    def __init__(self, contenido=None, error=None):
        self.contenido = contenido
        self.error = error
        self.pedidos = []
        self.opciones = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def __call__(self, **opciones):
        self.opciones = opciones
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def _create(self, **pedido):
        self.pedidos.append(pedido)
        if self.error:
            raise self.error
        mensaje = SimpleNamespace(content=self.contenido)
        return SimpleNamespace(choices=[SimpleNamespace(message=mensaje)])


@pytest.fixture
def con_clave(monkeypatch):
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "clave-de-prueba")


@pytest.fixture
def openrouter(monkeypatch, con_clave):
    """Devuelve una función para configurar la respuesta del modelo."""

    def configurar(contenido=None, error=None):
        if isinstance(contenido, dict):
            contenido = json.dumps(contenido)
        cliente = ClienteFalso(contenido, error)
        monkeypatch.setattr(extraccion, "AsyncOpenAI", cliente)
        return cliente

    return configurar


def _enviar(client, headers):
    return client.post(URL, files={"foto": ("f.jpg", JPEG, "image/jpeg")}, headers=headers)


# ------------------------------------------------------------------ endpoint


def test_devuelve_lo_que_leyo_el_modelo(client, headers_auth, openrouter):
    openrouter(RESPUESTA_COMPLETA)

    respuesta = _enviar(client, headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json()["extraccion"] == {
        "lote": "L61050467",
        "fecha_vencimiento": "2027-03-15",
        "fecha_cruda": "VEN 15/03/27",
        "venc_precision": "dia",
        "confianza": "alta",
        "notas": None,
    }


def test_envia_la_foto_al_modelo_configurado(client, headers_auth, openrouter):
    cliente = openrouter(RESPUESTA_COMPLETA)

    _enviar(client, headers_auth)

    pedido = cliente.pedidos[0]
    assert pedido["model"] == get_settings().openrouter_model
    assert pedido["response_format"] == {"type": "json_object"}
    imagen = pedido["messages"][1]["content"][1]["image_url"]["url"]
    assert imagen.startswith("data:image/jpeg;base64,")
    assert cliente.opciones["api_key"] == "clave-de-prueba"


def test_sin_clave_responde_503(client, headers_auth, monkeypatch):
    monkeypatch.setattr(get_settings(), "openrouter_api_key", None)

    respuesta = _enviar(client, headers_auth)

    assert respuesta.status_code == 503
    assert respuesta.json()["detail"] == "La lectura automática de fotos no está configurada"


def test_error_de_openrouter_responde_502(client, headers_auth, openrouter):
    openrouter(error=APITimeoutError(request=None))

    respuesta = _enviar(client, headers_auth)

    assert respuesta.status_code == 502
    assert "a mano" in respuesta.json()["detail"]


@pytest.mark.parametrize("contenido", ["no es json", "", None, "[1, 2]"])
def test_respuesta_ilegible_responde_502(client, headers_auth, openrouter, contenido):
    openrouter(contenido)

    assert _enviar(client, headers_auth).status_code == 502


def test_tolera_json_dentro_de_un_bloque_de_codigo(client, headers_auth, openrouter):
    openrouter("```json\n" + json.dumps(RESPUESTA_COMPLETA) + "\n```")

    respuesta = _enviar(client, headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json()["extraccion"]["lote"] == "L61050467"


def test_confianza_desconocida_cuenta_como_baja(client, headers_auth, openrouter):
    openrouter({**RESPUESTA_COMPLETA, "confianza": "muy alta"})

    assert _enviar(client, headers_auth).json()["extraccion"]["confianza"] == "baja"


def test_campos_faltantes_o_vacios_quedan_en_null(client, headers_auth, openrouter):
    openrouter({"lote": "  ", "notas": "Código cortado por el borde"})

    extraido = _enviar(client, headers_auth).json()["extraccion"]

    assert extraido == {
        "lote": None,
        "fecha_vencimiento": None,
        "fecha_cruda": None,
        "venc_precision": "nulo",
        "confianza": "baja",
        "notas": "Código cortado por el borde",
    }


def test_sin_token_no_llama_al_modelo(client, openrouter):
    cliente = openrouter(RESPUESTA_COMPLETA)

    assert client.post(URL, files={"foto": ("f.jpg", JPEG, "image/jpeg")}).status_code == 401
    assert cliente.pedidos == []


# ------------------------------------------------------------------ fechas


def _datos(**cambios):
    return extraccion._RespuestaModelo(**{**RESPUESTA_COMPLETA, **cambios})


@pytest.mark.parametrize(
    ("cambios", "esperada"),
    [
        ({}, date(2027, 3, 15)),
        ({"venc_anio": 27}, date(2027, 3, 15)),
        # Solo mes y año: último día del mes
        ({"venc_precision": "mes", "venc_dia": None, "venc_mes": 5}, date(2027, 5, 31)),
        ({"venc_precision": "mes", "venc_dia": None, "venc_mes": 2, "venc_anio": 2028}, date(2028, 2, 29)),
        # Sin fecha, incompleta o imposible
        ({"venc_precision": "nulo"}, None),
        ({"venc_dia": None}, None),
        ({"venc_mes": None}, None),
        ({"venc_dia": 31, "venc_mes": 2}, None),
        ({"venc_mes": 13}, None),
    ],
)
def test_armar_fecha(cambios, esperada):
    assert extraccion.armar_fecha(_datos(**cambios)) == esperada


def test_el_502_incluye_la_causa_y_el_modelo(client, headers_auth, openrouter):
    openrouter("no es json")

    cuerpo = _enviar(client, headers_auth).json()

    assert cuerpo["modelo"] == get_settings().openrouter_model
    assert "formato esperado" in cuerpo["causa"]
    assert "clave-de-prueba" not in cuerpo["causa"]


def test_describe_un_error_de_openrouter_con_su_mensaje():
    import httpx2
    from openai import BadRequestError

    respuesta = httpx2.Response(400, request=httpx2.Request("POST", "https://openrouter.ai"))
    error = BadRequestError(
        "x", response=respuesta, body={"error": {"message": "modelo no válido", "code": 400}}
    )

    assert extraccion.describir_error(error) == "OpenRouter respondió 400: modelo no válido"


def test_openrouter_saturado_responde_429(client, headers_auth, openrouter):
    import httpx2
    from openai import RateLimitError

    respuesta = httpx2.Response(429, request=httpx2.Request("POST", "https://openrouter.ai"))
    openrouter(error=RateLimitError("x", response=respuesta, body=None))

    resultado = _enviar(client, headers_auth)

    assert resultado.status_code == 429
    assert resultado.json()["codigo"] == "lectura_saturada"
    assert resultado.headers["Retry-After"] == "30"
    # No gasta una lectura del plan.
    assert client.get("/auth/plan", headers=headers_auth).json()["lecturas_usadas"] == 0
