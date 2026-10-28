from sqlalchemy import select

from app.models.empresa import Empresa
from app.security import verificar_contrasena
from tests.conftest import headers_de

URL = "/empresas/"


def _datos(**cambios):
    datos = {"nombre": "Empresa Dos", "usuario": "empresa_dos", "contrasena": "clave1234"}
    return datos | cambios


def _crear_otra(client):
    """Crea una segunda empresa y devuelve (datos, headers con su token)."""
    otra = client.post(URL, json=_datos()).json()
    return otra, headers_de(otra["id"])


# --- POST /empresas (público) ---


def test_crear_empresa(client):
    respuesta = client.post(URL, json=_datos())

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "Empresa Dos"
    assert cuerpo["usuario"] == "empresa_dos"
    assert isinstance(cuerpo["id"], int)


def test_crear_empresa_no_devuelve_contrasena(client):
    respuesta = client.post(URL, json=_datos())

    assert "contrasena" not in respuesta.json()


def test_crear_empresa_guarda_contrasena_hasheada(client, db):
    empresa_id = client.post(URL, json=_datos()).json()["id"]

    guardada = db.get(Empresa, empresa_id).contrasena
    assert guardada != "clave1234"
    assert verificar_contrasena("clave1234", guardada)


def test_crear_empresa_usuario_duplicado(client, empresa_existente):
    respuesta = client.post(URL, json=_datos(usuario=empresa_existente["usuario"]))

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "El usuario 'empresa_uno' ya está en uso"


def test_crear_empresa_falta_campo(client):
    datos = _datos()
    del datos["usuario"]

    respuesta = client.post(URL, json=datos)

    assert respuesta.status_code == 422


def test_crear_empresa_contrasena_vacia(client):
    respuesta = client.post(URL, json=_datos(contrasena=""))

    assert respuesta.status_code == 422


def test_crear_empresa_contrasena_corta(client):
    respuesta = client.post(URL, json=_datos(contrasena="a" * 7))

    assert respuesta.status_code == 422


def test_crear_empresa_contrasena_minima(client):
    respuesta = client.post(URL, json=_datos(contrasena="a" * 8))

    assert respuesta.status_code == 201


def test_crear_empresa_contrasena_maxima(client):
    respuesta = client.post(URL, json=_datos(contrasena="a" * 128))

    assert respuesta.status_code == 201


def test_crear_empresa_contrasena_muy_larga(client):
    respuesta = client.post(URL, json=_datos(contrasena="a" * 129))

    assert respuesta.status_code == 422


def test_crear_empresa_usuario_muy_largo(client):
    respuesta = client.post(URL, json=_datos(usuario="u" * 51))

    assert respuesta.status_code == 422


def test_error_validacion_no_devuelve_contrasena(client):
    datos = _datos(contrasena="MiClaveSecreta")
    del datos["nombre"]

    respuesta = client.post(URL, json=datos)

    assert respuesta.status_code == 422
    assert "MiClaveSecreta" not in respuesta.text
    error = respuesta.json()["detail"][0]
    assert error["loc"] == ["body", "nombre"]
    assert "input" not in error


# --- GET /empresas (ya no existe) ---


def test_listar_empresas_no_existe(client, headers_auth):
    """El listado exponía el usuario de login de todas las empresas."""
    respuesta = client.get(URL, headers=headers_auth)

    assert respuesta.status_code == 405


# --- GET /empresas/{id} ---


def test_obtener_empresa(client, empresa_existente, headers_auth):
    respuesta = client.get(f"{URL}{empresa_existente['id']}", headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == empresa_existente


def test_obtener_empresa_sin_token(client, empresa_existente):
    respuesta = client.get(f"{URL}{empresa_existente['id']}")

    assert respuesta.status_code == 401


def test_obtener_otra_empresa(client, empresa_existente, headers_auth):
    otra, _ = _crear_otra(client)

    respuesta = client.get(f"{URL}{otra['id']}", headers=headers_auth)

    assert respuesta.status_code == 403
    assert "usuario" not in respuesta.json()


def test_obtener_empresa_inexistente(client, headers_auth):
    respuesta = client.get(f"{URL}999999", headers=headers_auth)

    assert respuesta.status_code == 403


def test_obtener_empresa_id_fuera_de_rango(client, headers_auth):
    respuesta = client.get(f"{URL}99999999999", headers=headers_auth)

    assert respuesta.status_code == 422


def test_obtener_empresa_id_cero(client, headers_auth):
    respuesta = client.get(f"{URL}0", headers=headers_auth)

    assert respuesta.status_code == 422


# --- PUT /empresas/{id} ---


def test_actualizar_empresa(client, db, empresa_existente, headers_auth):
    empresa_id = empresa_existente["id"]

    respuesta = client.put(
        f"{URL}{empresa_id}",
        json={"nombre": "Nuevo", "usuario": "nuevo_usuario"},
        headers=headers_auth,
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == {"id": empresa_id, "nombre": "Nuevo", "usuario": "nuevo_usuario"}
    assert verificar_contrasena("secreta123", db.get(Empresa, empresa_id).contrasena)


def test_actualizar_empresa_con_contrasena_rechazada(client, db, empresa_existente, headers_auth):
    empresa_id = empresa_existente["id"]

    respuesta = client.put(
        f"{URL}{empresa_id}",
        json={"nombre": "Nuevo", "usuario": "nuevo_usuario", "contrasena": "nueva12345"},
        headers=headers_auth,
    )

    assert respuesta.status_code == 422
    assert verificar_contrasena("secreta123", db.get(Empresa, empresa_id).contrasena)


def test_actualizar_empresa_usuario_duplicado(client, empresa_existente):
    otra, headers_otra = _crear_otra(client)

    respuesta = client.put(
        f"{URL}{otra['id']}",
        json={"nombre": "Cambio", "usuario": "empresa_uno"},
        headers=headers_otra,
    )

    assert respuesta.status_code == 409
    assert client.get(f"{URL}{otra['id']}", headers=headers_otra).json() == otra


def test_actualizar_empresa_falta_campo(client, empresa_existente, headers_auth):
    respuesta = client.put(
        f"{URL}{empresa_existente['id']}", json={"nombre": "Solo nombre"}, headers=headers_auth
    )

    assert respuesta.status_code == 422


def test_actualizar_empresa_sin_token(client, empresa_existente):
    respuesta = client.put(
        f"{URL}{empresa_existente['id']}", json={"nombre": "Nuevo", "usuario": "nuevo"}
    )

    assert respuesta.status_code == 401


def test_actualizar_otra_empresa(client, empresa_existente, headers_auth):
    otra, _ = _crear_otra(client)

    respuesta = client.put(f"{URL}{otra['id']}", json={"nombre": "Hackeada", "usuario": "empresa_dos"}, headers=headers_auth)

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "No tienes permiso sobre esta empresa"


# --- PATCH /empresas/{id} ---


def test_patch_un_campo(client, empresa_existente, headers_auth):
    respuesta = client.patch(
        f"{URL}{empresa_existente['id']}", json={"nombre": "Editada"}, headers=headers_auth
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == empresa_existente | {"nombre": "Editada"}


def test_patch_contrasena_rechazada(client, db, empresa_existente, headers_auth):
    empresa_id = empresa_existente["id"]

    respuesta = client.patch(
        f"{URL}{empresa_id}", json={"contrasena": "otra12345"}, headers=headers_auth
    )

    assert respuesta.status_code == 422
    assert verificar_contrasena("secreta123", db.get(Empresa, empresa_id).contrasena)


def test_patch_null_se_ignora(client, empresa_existente, headers_auth):
    respuesta = client.patch(
        f"{URL}{empresa_existente['id']}", json={"usuario": None}, headers=headers_auth
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == empresa_existente


def test_patch_body_vacio(client, db, empresa_existente, headers_auth):
    empresa_id = empresa_existente["id"]
    hash_antes = db.get(Empresa, empresa_id).contrasena

    respuesta = client.patch(f"{URL}{empresa_id}", json={}, headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == empresa_existente
    assert db.get(Empresa, empresa_id).contrasena == hash_antes


def test_patch_usuario_duplicado(client, empresa_existente):
    otra, headers_otra = _crear_otra(client)

    respuesta = client.patch(
        f"{URL}{otra['id']}", json={"usuario": "empresa_uno"}, headers=headers_otra
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "El usuario 'empresa_uno' ya está en uso"
    assert client.get(f"{URL}{otra['id']}", headers=headers_otra).json() == otra


def test_patch_sin_token(client, empresa_existente):
    respuesta = client.patch(f"{URL}{empresa_existente['id']}", json={"nombre": "x"})

    assert respuesta.status_code == 401


def test_patch_otra_empresa(client, empresa_existente, headers_auth):
    otra, headers_otra = _crear_otra(client)

    respuesta = client.patch(f"{URL}{otra['id']}", json={"nombre": "Hackeada"}, headers=headers_auth)

    assert respuesta.status_code == 403
    assert client.get(f"{URL}{otra['id']}", headers=headers_otra).json() == otra


# --- DELETE /empresas/{id} ---


def test_eliminar_empresa(client, db, empresa_existente, headers_auth):
    respuesta = client.delete(f"{URL}{empresa_existente['id']}", headers=headers_auth)

    assert respuesta.status_code == 204
    assert db.scalars(select(Empresa)).all() == []


def test_eliminar_empresa_sin_token(client, empresa_existente):
    respuesta = client.delete(f"{URL}{empresa_existente['id']}")

    assert respuesta.status_code == 401


def test_eliminar_otra_empresa(client, db, empresa_existente, headers_auth):
    otra, _ = _crear_otra(client)

    respuesta = client.delete(f"{URL}{otra['id']}", headers=headers_auth)

    assert respuesta.status_code == 403
    assert db.get(Empresa, otra["id"]) is not None
