from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

import pytest

from app import cli
from app.config import get_settings
from app.crud import plan as crud_plan
from app.exceptions import LecturaFallida
from app.models.empresa import Empresa
from app.models.lectura_foto import LecturaFoto
from app.routers import trackings as router_trackings
from tests.test_fotos import EXTRACCION, JPEG

URL_FOTO = "/trackings/photo"
URL_PLAN = "/auth/plan"
LECTURAS_DEMO = 10


@pytest.fixture(autouse=True)
def lectura_simulada(monkeypatch):
    """Cuenta las llamadas al modelo sin llamar a OpenRouter."""
    llamadas = []

    async def falsa(contenido, tipo):
        llamadas.append(tipo)
        return EXTRACCION

    monkeypatch.setattr(router_trackings, "extraer_datos", falsa)
    return llamadas


@pytest.fixture(autouse=True)
def sin_limite_por_minuto(monkeypatch):
    """La ráfaga se prueba aparte: aquí no estorba al gastar varias lecturas seguidas."""
    monkeypatch.setattr(get_settings(), "lecturas_por_minuto", 1_000)


@pytest.fixture
def soporte(monkeypatch):
    monkeypatch.setattr(get_settings(), "soporte_whatsapp", "573001234567")
    monkeypatch.setattr(get_settings(), "soporte_correo", "soporte@scanproducts.co")


@pytest.fixture
def empresa(db, empresa_existente) -> Empresa:
    """La empresa del token, con la demo desde hace una hora: así cuentan las lecturas de _gastar."""
    empresa = db.get(Empresa, empresa_existente["id"])
    empresa.plan_desde -= timedelta(hours=1)
    db.commit()
    return empresa


def _enviar(client, headers):
    return client.post(URL_FOTO, files={"foto": ("f.jpg", JPEG, "image/jpeg")}, headers=headers)


def _gastar(db, empresa_id: int, cantidad: int, cuando: datetime | None = None) -> None:
    """Registra lecturas ya hechas (por defecto, hace dos minutos: fuera de la ráfaga)."""
    cuando = cuando or datetime.now(UTC) - timedelta(minutes=2)
    db.add_all(LecturaFoto(empresa_id=empresa_id, creada_en=cuando) for _ in range(cantidad))
    db.commit()


# ---------------------------------------------------------------- GET /auth/plan


def test_una_empresa_nueva_empieza_en_la_demo(client, headers_auth, planes):
    plan = client.get(URL_PLAN, headers=headers_auth).json()

    assert plan["plan_id"] == planes["demo"].id
    assert plan["nombre"] == "Demo"
    assert plan["es_demo"] is True
    assert plan["lecturas_limite"] == LECTURAS_DEMO
    assert plan["lecturas_usadas"] == 0
    assert plan["lecturas_restantes"] == LECTURAS_DEMO
    assert plan["plan_hasta"] is None
    assert plan["vencido"] is False
    assert plan["motivo"] is None
    assert plan["mensaje"] is None


def test_sin_demo_activa_la_empresa_nueva_queda_sin_plan(client, db, planes):
    planes["demo"].activo = False
    db.commit()

    respuesta = client.post(
        "/empresas/", json={"nombre": "Nueva", "usuario": "nueva", "contrasena": "secreta123"}
    )

    assert db.get(Empresa, respuesta.json()["id"]).plan_id is None


def test_plan_sin_token(client):
    assert client.get(URL_PLAN).status_code == 401


def test_el_plan_trae_el_contacto_de_soporte(client, headers_auth, soporte):
    assert client.get(URL_PLAN, headers=headers_auth).json()["soporte"] == {
        "whatsapp": "573001234567",
        "correo": "soporte@scanproducts.co",
    }


def test_soporte_sin_configurar(client, headers_auth, monkeypatch):
    monkeypatch.setattr(get_settings(), "soporte_whatsapp", None)
    monkeypatch.setattr(get_settings(), "soporte_correo", None)

    assert client.get(URL_PLAN, headers=headers_auth).json()["soporte"] == {"whatsapp": None, "correo": None}


# ---------------------------------------------------------------- consumo


def test_una_lectura_exitosa_cuenta(client, headers_auth):
    respuesta = _enviar(client, headers_auth)

    assert respuesta.json()["lecturas_restantes"] == LECTURAS_DEMO - 1
    assert client.get(URL_PLAN, headers=headers_auth).json()["lecturas_usadas"] == 1


def test_una_lectura_fallida_no_cuenta(client, headers_auth, monkeypatch):
    async def falla(contenido, tipo):
        raise LecturaFallida("simulada")

    monkeypatch.setattr(router_trackings, "extraer_datos", falla)

    assert _enviar(client, headers_auth).status_code == 502
    assert client.get(URL_PLAN, headers=headers_auth).json()["lecturas_usadas"] == 0


def test_una_foto_invalida_no_cuenta(client, headers_auth):
    client.post(URL_FOTO, files={"foto": ("f.jpg", b"no es foto", "image/jpeg")}, headers=headers_auth)

    assert client.get(URL_PLAN, headers=headers_auth).json()["lecturas_usadas"] == 0


def test_las_lecturas_de_otra_empresa_no_cuentan(client, db, headers_otra_empresa, empresa):
    _gastar(db, empresa.id, LECTURAS_DEMO)

    assert _enviar(client, headers_otra_empresa).status_code == 200


# ---------------------------------------------------------------- sin lecturas


def test_demo_agotada(client, db, headers_auth, empresa, lectura_simulada, soporte):
    _gastar(db, empresa.id, LECTURAS_DEMO)

    respuesta = _enviar(client, headers_auth)

    assert respuesta.status_code == 403
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "sin_lecturas"
    assert cuerpo["motivo"] == "agotado"
    assert cuerpo["soporte"] == {"whatsapp": "573001234567", "correo": "soporte@scanproducts.co"}
    assert "lecturas de prueba de tu plan Demo" in cuerpo["detail"]
    assert "soporte" in cuerpo["detail"]
    assert lectura_simulada == []  # no se gasta una llamada al modelo


def test_demo_renombrada_usa_su_nombre(client, db, headers_auth, empresa, planes):
    planes["demo"].nombre = "Inicial"
    _gastar(db, empresa.id, LECTURAS_DEMO)

    detalle = _enviar(client, headers_auth).json()["detail"]

    assert "de tu plan Inicial" in detalle
    assert "demo" not in detalle.lower()


def test_la_ultima_lectura_de_la_demo_si_pasa(client, db, headers_auth, empresa):
    _gastar(db, empresa.id, LECTURAS_DEMO - 1)

    respuesta = _enviar(client, headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json()["lecturas_restantes"] == 0
    assert _enviar(client, headers_auth).status_code == 403


def test_plan_pago_agotado(client, db, headers_auth, empresa, planes):
    crud_plan.activar(db, empresa, planes["basico"])
    empresa.plan_desde -= timedelta(hours=1)
    _gastar(db, empresa.id, planes["basico"].lecturas)

    respuesta = _enviar(client, headers_auth)

    assert respuesta.status_code == 403
    assert respuesta.json()["motivo"] == "agotado"
    assert "plan Básico" in respuesta.json()["detail"]


def test_plan_vencido(client, db, headers_auth, empresa, planes):
    crud_plan.activar(db, empresa, planes["pro"])
    empresa.plan_hasta = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    plan = client.get(URL_PLAN, headers=headers_auth).json()
    respuesta = _enviar(client, headers_auth)

    assert plan["vencido"] is True
    assert plan["lecturas_restantes"] == 0
    assert plan["motivo"] == "vencido"
    assert respuesta.status_code == 403
    assert "venció" in respuesta.json()["detail"]
    assert plan["mensaje"] == respuesta.json()["detail"]


def test_sin_plan(client, db, headers_auth, empresa, lectura_simulada):
    crud_plan.activar(db, empresa, None)

    plan = client.get(URL_PLAN, headers=headers_auth).json()
    respuesta = _enviar(client, headers_auth)

    assert plan["plan_id"] is None
    assert plan["nombre"] is None
    assert plan["lecturas_restantes"] == 0
    assert plan["motivo"] == "sin_plan"
    assert respuesta.status_code == 403
    assert respuesta.json()["motivo"] == "sin_plan"
    assert "no tiene un plan" in respuesta.json()["detail"]
    assert lectura_simulada == []


def test_editar_las_lecturas_de_un_plan_aplica_al_periodo_actual(client, db, headers_auth, empresa, planes):
    _gastar(db, empresa.id, 3, cuando=datetime.now(UTC))
    planes["demo"].lecturas = 3
    db.commit()

    assert _enviar(client, headers_auth).status_code == 403


# ---------------------------------------------------------------- ráfaga


def test_limite_por_minuto(client, db, headers_auth, empresa, monkeypatch, lectura_simulada):
    monkeypatch.setattr(get_settings(), "lecturas_por_minuto", 2)
    _gastar(db, empresa.id, 2, cuando=datetime.now(UTC) - timedelta(seconds=20))

    respuesta = _enviar(client, headers_auth)

    assert respuesta.status_code == 429
    assert respuesta.json()["codigo"] == "demasiadas_lecturas"
    # La más vieja salió hace 20 s: falta ~40 s para que salga de la ventana.
    assert 38 <= int(respuesta.headers["Retry-After"]) <= 41
    assert lectura_simulada == []


def test_las_lecturas_de_hace_mas_de_un_minuto_no_frenan(client, db, headers_auth, empresa, monkeypatch):
    monkeypatch.setattr(get_settings(), "lecturas_por_minuto", 2)
    _gastar(db, empresa.id, 2)  # hace dos minutos

    assert _enviar(client, headers_auth).status_code == 200


# ---------------------------------------------------------------- activar


def test_activar_un_plan_reinicia_el_contador(client, db, headers_auth, empresa, planes):
    _gastar(db, empresa.id, LECTURAS_DEMO)

    crud_plan.activar(db, empresa, planes["basico"])
    plan = client.get(URL_PLAN, headers=headers_auth).json()

    assert plan["nombre"] == "Básico"
    assert plan["es_demo"] is False
    assert plan["lecturas_usadas"] == 0
    assert plan["lecturas_restantes"] == planes["basico"].lecturas
    assert _enviar(client, headers_auth).status_code == 200


def test_un_plan_pago_dura_sus_dias(db, empresa, planes):
    crud_plan.activar(db, empresa, planes["pro"])

    assert empresa.plan_hasta - empresa.plan_desde == timedelta(days=30)


def test_volver_a_la_demo_no_vence(db, empresa, planes):
    crud_plan.activar(db, empresa, planes["pro"])
    crud_plan.activar(db, empresa, planes["demo"])

    assert empresa.plan_hasta is None


def test_quitar_el_plan(db, empresa):
    crud_plan.activar(db, empresa, None)

    assert (empresa.plan_id, empresa.plan_desde, empresa.plan_hasta) == (None, None, None)


@pytest.mark.parametrize("nombre", ["basico", "Básico", " BASICO "])
def test_buscar_un_plan_ignora_tildes_y_mayusculas(db, planes, nombre):
    assert crud_plan.buscar(db, nombre) is planes["basico"]


# ---------------------------------------------------------------- consola


@pytest.fixture
def consola(db, monkeypatch):
    """La consola usa la sesión del test en vez de abrir una propia."""
    monkeypatch.setattr(cli, "SessionLocal", lambda: nullcontext(db))


def test_consola_activa_un_plan(consola, empresa, capsys):
    assert cli.main(["plan", "empresa_uno", "pro"]) == 0

    assert empresa.plan.nombre == "Pro"
    assert "Plan activado" in capsys.readouterr().out


def test_consola_quita_el_plan(consola, empresa, capsys):
    assert cli.main(["quitar", "empresa_uno"]) == 0

    assert empresa.plan is None
    assert "sin plan" in capsys.readouterr().out


def test_consola_muestra_el_plan(consola, empresa, capsys):
    assert cli.main(["ver", "empresa_uno"]) == 0

    salida = capsys.readouterr().out
    assert "Demo" in salida
    assert f"quedan {LECTURAS_DEMO}" in salida


def test_consola_lista_los_planes(consola, capsys):
    assert cli.main(["planes"]) == 0

    salida = capsys.readouterr().out
    assert "Básico" in salida and "Pro" in salida and "[demo]" in salida


def test_consola_usuario_inexistente(consola, capsys):
    assert cli.main(["ver", "no_existe"]) == 1
    assert "No existe" in capsys.readouterr().err


def test_consola_rechaza_un_plan_inexistente(consola, empresa, capsys):
    assert cli.main(["plan", "empresa_uno", "oro"]) == 1
    assert "No existe el plan" in capsys.readouterr().err


# ---------------------------------------------------------------- GET /auth/planes


def test_planes_disponibles_sin_la_demo(client, headers_auth):
    planes = client.get("/auth/planes", headers=headers_auth).json()

    assert [(p["nombre"], p["precio"], p["lecturas"], p["dias"]) for p in planes] == [
        ("Básico", 15_000, 500, 30),
        ("Pro", 28_000, 1_000, 30),
    ]
    assert set(planes[0]) == {"id", "nombre", "precio", "lecturas", "dias"}


def test_planes_disponibles_sin_los_desactivados(client, db, headers_auth, planes):
    planes["pro"].activo = False
    db.commit()

    nombres = [p["nombre"] for p in client.get("/auth/planes", headers=headers_auth).json()]

    assert nombres == ["Básico"]


def test_planes_disponibles_sin_token(client):
    assert client.get("/auth/planes").status_code == 401
