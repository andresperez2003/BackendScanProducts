import pytest

from app.routers import trackings as router_trackings
from app.schemas.tracking import ExtraccionFoto
from app.services import fotos

URL = "/trackings/photo"

EXTRACCION = ExtraccionFoto(
    lote="L61050467",
    fecha_vencimiento="2027-05-31",
    fecha_cruda="05/2027",
    venc_precision="mes",
    confianza="media",
    notas=None,
)

# Solo importan los primeros bytes (la "firma"): el resto puede ser relleno.
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 200


@pytest.fixture(autouse=True)
def lectura_simulada(monkeypatch):
    """Estos tests son de la validación: no llaman a OpenRouter (ver test_extraccion.py)."""
    recibidas = []

    async def falsa(contenido, tipo):
        recibidas.append((contenido, tipo))
        return EXTRACCION

    monkeypatch.setattr(router_trackings, "extraer_datos", falsa)
    return recibidas


def _enviar(client, headers, contenido, nombre="foto.jpg", tipo="image/jpeg"):
    return client.post(URL, files={"foto": (nombre, contenido, tipo)}, headers=headers)


@pytest.mark.parametrize(
    ("contenido", "tipo_esperado"),
    [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp")],
)
def test_recibe_foto_valida(client, headers_auth, contenido, tipo_esperado):
    respuesta = _enviar(client, headers_auth, contenido)

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "recibida": True,
        "nombre": "foto.jpg",
        "tipo": tipo_esperado,
        "tamano_bytes": len(contenido),
        "extraccion": {
            "lote": "L61050467",
            "fecha_vencimiento": "2027-05-31",
            "fecha_cruda": "05/2027",
            "venc_precision": "mes",
            "confianza": "media",
            "notas": None,
        },
        "lecturas_restantes": 9,
    }


def test_al_modelo_le_llega_la_foto_con_su_tipo_real(client, headers_auth, lectura_simulada):
    _enviar(client, headers_auth, PNG, tipo="image/jpeg")

    assert lectura_simulada == [(PNG, "image/png")]


def test_una_foto_invalida_no_llega_al_modelo(client, headers_auth, lectura_simulada):
    _enviar(client, headers_auth, b"esto no es una foto")

    assert lectura_simulada == []


def test_el_tipo_sale_del_contenido_no_del_cliente(client, headers_auth):
    """Un PNG enviado como 'image/jpeg' se reporta como PNG."""
    respuesta = _enviar(client, headers_auth, PNG, tipo="image/jpeg")

    assert respuesta.json()["tipo"] == "image/png"


def test_rechaza_archivo_que_no_es_imagen(client, headers_auth):
    """Aunque diga ser image/jpeg, un texto no pasa la validación."""
    respuesta = _enviar(client, headers_auth, b"esto no es una foto", tipo="image/jpeg")

    assert respuesta.status_code == 415
    assert respuesta.json()["detail"] == "La foto debe ser una imagen JPEG, PNG o WebP"


def test_rechaza_foto_vacia(client, headers_auth):
    respuesta = _enviar(client, headers_auth, b"")

    assert respuesta.status_code == 422


def test_rechaza_foto_muy_grande(client, headers_auth, monkeypatch):
    monkeypatch.setattr(fotos, "MAXIMO_BYTES", 100)

    respuesta = _enviar(client, headers_auth, JPEG)

    assert respuesta.status_code == 413
    assert "MB" in respuesta.json()["detail"]


def test_foto_justo_en_el_limite(client, headers_auth, monkeypatch):
    monkeypatch.setattr(fotos, "MAXIMO_BYTES", len(JPEG))

    assert _enviar(client, headers_auth, JPEG).status_code == 200


def test_falta_la_foto(client, headers_auth):
    respuesta = client.post(URL, headers=headers_auth)

    assert respuesta.status_code == 422


def test_campo_con_otro_nombre(client, headers_auth):
    respuesta = client.post(URL, files={"imagen": ("f.jpg", JPEG, "image/jpeg")}, headers=headers_auth)

    assert respuesta.status_code == 422


def test_foto_sin_token(client):
    respuesta = client.post(URL, files={"foto": ("f.jpg", JPEG, "image/jpeg")})

    assert respuesta.status_code == 401


def test_la_foto_no_se_guarda(client, headers_auth, db):
    """Leerla no crea el seguimiento: eso lo hace el usuario después de revisar."""
    from sqlalchemy import func, select

    from app.models.tracking import Tracking

    _enviar(client, headers_auth, JPEG)

    assert db.scalar(select(func.count()).select_from(Tracking)) == 0
