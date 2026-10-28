from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app import cli
from app.crud import administrador as crud_admin
from app.crud import plan as crud_plan
from app.models.administrador import Administrador
from app.models.empresa import Empresa
from app.models.lectura_foto import LecturaFoto
from app.security import crear_token
from tests.conftest import headers_de

LOGIN = "/admin/auth/login"
ME = "/admin/auth/me"
EMPRESAS = "/admin/empresas"
PLANES = "/admin/planes"


@pytest.fixture
def admin(db) -> Administrador:
    return crud_admin.crear(db, "Equipo ScanProducts", "jefe", "clave-admin-1")


@pytest.fixture
def headers_admin(admin):
    return {"Authorization": f"Bearer {crear_token(admin.id, 0, tipo='admin')}"}


def _login(client, usuario, contrasena):
    return client.post(LOGIN, data={"username": usuario, "password": contrasena})


def _gastar(db, empresa_id: int, cantidad: int, cuando: datetime | None = None) -> None:
    cuando = cuando or datetime.now(UTC)
    db.add_all(LecturaFoto(empresa_id=empresa_id, creada_en=cuando) for _ in range(cantidad))
    db.commit()


# ---------------------------------------------------------------- login y tokens


def test_login_correcto(client, admin):
    token = _login(client, "jefe", "clave-admin-1").json()["access_token"]

    respuesta = client.get(ME, headers={"Authorization": f"Bearer {token}"})

    assert respuesta.status_code == 200
    assert respuesta.json() == {"id": admin.id, "nombre": "Equipo ScanProducts", "usuario": "jefe"}


def test_login_incorrecto(client, admin):
    respuesta = _login(client, "jefe", "otra-clave")

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == "Usuario o contraseña incorrectos"


def test_una_empresa_no_puede_entrar_por_el_login_de_admin(client, empresa_existente):
    assert _login(client, "empresa_uno", "secreta123").status_code == 401


def test_login_bloquea_tras_5_fallos(client, admin):
    for _ in range(4):
        _login(client, "jefe", "otra-clave")

    assert _login(client, "jefe", "otra-clave").status_code == 429
    assert _login(client, "jefe", "clave-admin-1").status_code == 429


def test_el_bloqueo_del_admin_no_bloquea_a_una_empresa_con_el_mismo_usuario(client, admin):
    client.post("/empresas/", json={"nombre": "Otra", "usuario": "jefe", "contrasena": "secreta123"})
    for _ in range(5):
        _login(client, "jefe", "otra-clave")

    assert client.post("/auth/login", data={"username": "jefe", "password": "secreta123"}).status_code == 200


def test_sin_token(client):
    assert client.get(EMPRESAS).status_code == 401


def test_token_de_empresa_no_entra_al_panel(client, headers_auth):
    assert client.get(EMPRESAS, headers=headers_auth).status_code == 401
    assert client.get(ME, headers=headers_auth).status_code == 401


def test_token_de_admin_no_entra_a_la_app(client, headers_admin):
    assert client.get("/auth/me", headers=headers_admin).status_code == 401
    assert client.get("/products/", headers=headers_admin).status_code == 401


def test_token_de_admin_con_el_id_de_una_empresa_no_la_suplanta(client, empresa_existente):
    """Un token de admin cuyo id coincide con el de una empresa sigue sin servir en la app."""
    token = crear_token(empresa_existente["id"], 0, tipo="admin")

    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_cambiar_contrasena_invalida_los_tokens_anteriores(client, admin, headers_admin):
    respuesta = client.post(
        "/admin/auth/cambiar-contrasena",
        json={"contrasena_actual": "clave-admin-1", "contrasena_nueva": "clave-admin-2"},
        headers=headers_admin,
    )

    assert respuesta.status_code == 200
    assert client.get(ME, headers=headers_admin).status_code == 401
    nuevo = {"Authorization": f"Bearer {respuesta.json()['access_token']}"}
    assert client.get(ME, headers=nuevo).status_code == 200
    assert _login(client, "jefe", "clave-admin-2").status_code == 200


def test_cambiar_contrasena_con_la_actual_incorrecta(client, headers_admin):
    respuesta = client.post(
        "/admin/auth/cambiar-contrasena",
        json={"contrasena_actual": "mala", "contrasena_nueva": "clave-admin-2"},
        headers=headers_admin,
    )

    assert respuesta.status_code == 400


# ---------------------------------------------------------------- empresas


def test_listar_empresas_con_su_plan_y_consumo(client, db, headers_admin, empresa_existente, headers_otra_empresa):
    _gastar(db, empresa_existente["id"], 3)

    empresas = client.get(EMPRESAS, headers=headers_admin).json()

    assert [e["usuario"] for e in empresas] == ["empresa_ajena", "empresa_uno"]  # por nombre
    uno = empresas[1]
    assert uno["nombre"] == "Empresa Uno"
    assert uno["plan"]["nombre"] == "Demo"
    assert uno["plan"]["lecturas_usadas"] == 3
    assert uno["plan"]["lecturas_restantes"] == 7
    assert empresas[0]["plan"]["lecturas_usadas"] == 0
    assert "contrasena" not in uno


def test_listar_empresas_sin_plan(client, db, headers_admin, empresa_existente):
    crud_plan.activar(db, db.get(Empresa, empresa_existente["id"]), None)

    plan = client.get(EMPRESAS, headers=headers_admin).json()[0]["plan"]

    assert plan["plan_id"] is None
    assert plan["motivo"] == "sin_plan"


@pytest.mark.parametrize("buscar", ["uno", "UNO", "empresa_u"])
def test_buscar_empresas(client, headers_admin, empresa_existente, headers_otra_empresa, buscar):
    empresas = client.get(EMPRESAS, params={"buscar": buscar}, headers=headers_admin).json()

    assert [e["usuario"] for e in empresas] == ["empresa_uno"]


def test_buscar_trata_los_comodines_como_texto(client, headers_admin, empresa_existente):
    assert client.get(EMPRESAS, params={"buscar": "%"}, headers=headers_admin).json() == []


def test_obtener_empresa(client, headers_admin, empresa_existente):
    respuesta = client.get(f"{EMPRESAS}/{empresa_existente['id']}", headers=headers_admin)

    assert respuesta.status_code == 200
    assert respuesta.json()["usuario"] == "empresa_uno"


def test_obtener_empresa_inexistente(client, headers_admin):
    respuesta = client.get(f"{EMPRESAS}/999999", headers=headers_admin)

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Empresa no encontrada"


# ---------------------------------------------------------------- asignar plan


def _asignar(client, headers, empresa_id, plan_id):
    return client.put(f"{EMPRESAS}/{empresa_id}/plan", json={"plan_id": plan_id}, headers=headers)


def test_asignar_un_plan(client, db, headers_admin, headers_auth, empresa_existente, planes):
    _gastar(db, empresa_existente["id"], 10, cuando=datetime.now(UTC) - timedelta(seconds=1))

    respuesta = _asignar(client, headers_admin, empresa_existente["id"], planes["basico"].id)

    assert respuesta.status_code == 200
    plan = respuesta.json()["plan"]
    assert plan["nombre"] == "Básico"
    assert plan["lecturas_usadas"] == 0
    assert plan["lecturas_restantes"] == 500
    hasta = datetime.fromisoformat(plan["plan_hasta"])
    assert hasta - datetime.fromisoformat(plan["plan_desde"]) == timedelta(days=30)
    # La empresa lo ve en su propio /auth/plan.
    assert client.get("/auth/plan", headers=headers_auth).json()["nombre"] == "Básico"


def test_renovar_el_mismo_plan_empieza_otro_periodo(client, db, headers_admin, empresa_existente, planes):
    _asignar(client, headers_admin, empresa_existente["id"], planes["pro"].id)
    empresa = db.get(Empresa, empresa_existente["id"])
    empresa.plan_hasta = datetime.now(UTC) - timedelta(days=1)  # vencido
    db.commit()

    plan = _asignar(client, headers_admin, empresa_existente["id"], planes["pro"].id).json()["plan"]

    assert plan["vencido"] is False
    assert plan["lecturas_restantes"] == 1000


def test_quitar_el_plan(client, headers_admin, empresa_existente):
    plan = _asignar(client, headers_admin, empresa_existente["id"], None).json()["plan"]

    assert plan["plan_id"] is None
    assert plan["motivo"] == "sin_plan"


def test_asignar_un_plan_desactivado(client, db, headers_admin, empresa_existente, planes):
    planes["pro"].activo = False
    db.commit()

    respuesta = _asignar(client, headers_admin, empresa_existente["id"], planes["pro"].id)

    assert respuesta.status_code == 409
    assert "desactivado" in respuesta.json()["detail"]


def test_asignar_un_plan_inexistente(client, headers_admin, empresa_existente):
    assert _asignar(client, headers_admin, empresa_existente["id"], 999999).status_code == 404


def test_asignar_un_plan_a_una_empresa_inexistente(client, headers_admin, planes):
    assert _asignar(client, headers_admin, 999999, planes["pro"].id).status_code == 404


def test_asignar_plan_rechaza_campos_extra(client, headers_admin, empresa_existente, planes):
    respuesta = client.put(
        f"{EMPRESAS}/{empresa_existente['id']}/plan",
        json={"plan_id": planes["pro"].id, "plan_hasta": "2099-01-01"},
        headers=headers_admin,
    )

    assert respuesta.status_code == 422


# ---------------------------------------------------------------- consumo


def test_consumo_por_dia(client, db, headers_admin, empresa_existente, headers_otra_empresa):
    ahora = datetime.now(UTC)
    _gastar(db, empresa_existente["id"], 2, cuando=ahora)
    _gastar(db, empresa_existente["id"], 3, cuando=ahora - timedelta(days=2))
    _gastar(db, empresa_existente["id"], 4, cuando=ahora - timedelta(days=10))  # fuera de los 7 días
    otra = db.scalar(select(Empresa).where(Empresa.usuario == "empresa_ajena"))
    _gastar(db, otra.id, 5, cuando=ahora)

    consumo = client.get(
        f"{EMPRESAS}/{empresa_existente['id']}/consumo", params={"dias": 7}, headers=headers_admin
    ).json()

    assert consumo["total"] == 5
    assert len(consumo["por_dia"]) == 7
    assert consumo["por_dia"][-1] == {"fecha": ahora.date().isoformat(), "lecturas": 2}
    assert consumo["por_dia"][-3] == {"fecha": (ahora - timedelta(days=2)).date().isoformat(), "lecturas": 3}
    assert sum(d["lecturas"] for d in consumo["por_dia"]) == 5


def test_consumo_por_defecto_son_30_dias(client, headers_admin, empresa_existente):
    consumo = client.get(f"{EMPRESAS}/{empresa_existente['id']}/consumo", headers=headers_admin).json()

    assert len(consumo["por_dia"]) == 30
    assert consumo["total"] == 0


@pytest.mark.parametrize("dias", [0, 367])
def test_consumo_rechaza_dias_fuera_de_rango(client, headers_admin, empresa_existente, dias):
    respuesta = client.get(
        f"{EMPRESAS}/{empresa_existente['id']}/consumo", params={"dias": dias}, headers=headers_admin
    )

    assert respuesta.status_code == 422


# ---------------------------------------------------------------- planes

NUEVO = {"nombre": "Empresarial", "precio": 50_000, "lecturas": 2_500, "dias": 30}


def test_listar_planes_con_cuantas_empresas_los_tienen(client, headers_admin, empresa_existente, headers_otra_empresa):
    planes = client.get(PLANES, headers=headers_admin).json()

    assert [p["nombre"] for p in planes] == ["Demo", "Básico", "Pro"]  # por precio
    demo = planes[0]
    assert demo["es_demo"] is True
    assert demo["empresas"] == 2
    assert planes[1] == {
        "id": planes[1]["id"],
        "nombre": "Básico",
        "precio": 15_000,
        "lecturas": 500,
        "dias": 30,
        "activo": True,
        "es_demo": False,
        "empresas": 0,
    }


def test_crear_plan(client, headers_admin):
    respuesta = client.post(PLANES, json=NUEVO, headers=headers_admin)

    assert respuesta.status_code == 201
    assert respuesta.json() | {"id": 0} == {**NUEVO, "id": 0, "activo": True, "es_demo": False, "empresas": 0}


def test_crear_plan_sin_vencimiento(client, headers_admin):
    respuesta = client.post(PLANES, json={**NUEVO, "dias": None}, headers=headers_admin)

    assert respuesta.status_code == 201
    assert respuesta.json()["dias"] is None


@pytest.mark.parametrize("nombre", ["Pro", "pro", "Basico", "  Básico  "])
def test_crear_plan_con_nombre_repetido(client, headers_admin, nombre):
    respuesta = client.post(PLANES, json={**NUEVO, "nombre": nombre}, headers=headers_admin)

    assert respuesta.status_code == 409


def test_crear_plan_no_puede_ser_demo(client, headers_admin):
    assert client.post(PLANES, json={**NUEVO, "es_demo": True}, headers=headers_admin).status_code == 422


@pytest.mark.parametrize(
    "cambio",
    [{"precio": -1}, {"lecturas": -1}, {"dias": 0}, {"nombre": ""}, {"nombre": "   "}, {"nombre": "x" * 51}],
)
def test_crear_plan_rechaza_valores_invalidos(client, headers_admin, cambio):
    assert client.post(PLANES, json={**NUEVO, **cambio}, headers=headers_admin).status_code == 422


def test_editar_plan(client, headers_admin, planes):
    datos = {"nombre": "Básico", "precio": 18_000, "lecturas": 600, "dias": 30, "activo": True}

    respuesta = client.put(f"{PLANES}/{planes['basico'].id}", json=datos, headers=headers_admin)

    assert respuesta.status_code == 200
    assert respuesta.json()["precio"] == 18_000
    assert respuesta.json()["lecturas"] == 600


def test_editar_las_lecturas_cambia_el_cupo_de_quienes_lo_tienen(client, headers_admin, headers_auth, planes):
    datos = {"nombre": "Demo", "precio": 0, "lecturas": 25, "dias": None, "activo": True}

    client.put(f"{PLANES}/{planes['demo'].id}", json=datos, headers=headers_admin)

    assert client.get("/auth/plan", headers=headers_auth).json()["lecturas_restantes"] == 25


def test_desactivar_plan(client, headers_admin, planes):
    datos = {"nombre": "Pro", "precio": 28_000, "lecturas": 1_000, "dias": 30, "activo": False}

    respuesta = client.put(f"{PLANES}/{planes['pro'].id}", json=datos, headers=headers_admin)

    assert respuesta.json()["activo"] is False


def test_editar_plan_con_el_nombre_de_otro(client, headers_admin, planes):
    datos = {"nombre": "pro", "precio": 15_000, "lecturas": 500, "dias": 30, "activo": True}

    assert client.put(f"{PLANES}/{planes['basico'].id}", json=datos, headers=headers_admin).status_code == 409


def test_editar_plan_inexistente(client, headers_admin):
    assert client.put(f"{PLANES}/999999", json=NUEVO, headers=headers_admin).status_code == 404


# ---------------------------------------------------------------- consola


@pytest.fixture
def consola(db, monkeypatch):
    monkeypatch.setattr(cli, "SessionLocal", lambda: nullcontext(db))


def _contrasenas(monkeypatch, *respuestas):
    pendientes = list(respuestas)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: pendientes.pop(0))


def test_consola_crea_un_admin(consola, client, monkeypatch, capsys):
    _contrasenas(monkeypatch, "clave-segura-1", "clave-segura-1")

    assert cli.main(["crear-admin", "dueno", "--nombre", "Dueño"]) == 0

    assert "creado" in capsys.readouterr().out
    assert _login(client, "dueno", "clave-segura-1").status_code == 200


def test_consola_admin_contrasenas_distintas(consola, monkeypatch, capsys):
    _contrasenas(monkeypatch, "clave-segura-1", "clave-segura-2")

    assert cli.main(["crear-admin", "dueno"]) == 1
    assert "no coinciden" in capsys.readouterr().err


def test_consola_admin_contrasena_corta(consola, monkeypatch, capsys):
    _contrasenas(monkeypatch, "corta")

    assert cli.main(["crear-admin", "dueno"]) == 1
    assert "entre 8" in capsys.readouterr().err


def test_consola_admin_repetido(consola, admin, monkeypatch, capsys):
    _contrasenas(monkeypatch, "clave-segura-1", "clave-segura-1")

    assert cli.main(["crear-admin", "jefe"]) == 1
    assert "Ya existe" in capsys.readouterr().err


def test_consola_admin_usuario_muy_largo(consola, capsys):
    assert cli.main(["crear-admin", "x" * 45]) == 1
    assert "entre 1 y 44" in capsys.readouterr().err


def test_headers_de_empresa_siguen_funcionando(client, empresa_existente):
    """Los tokens de empresa (sin "tipo" o con tipo empresa) no cambian."""
    assert client.get("/auth/me", headers=headers_de(empresa_existente["id"])).status_code == 200
