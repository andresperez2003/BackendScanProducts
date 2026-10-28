import pytest

from app.crud import supplier as crud_supplier

URL = "/suppliers/"


# --- POST /suppliers ---


def test_crear_supplier(client, headers_auth):
    respuesta = client.post(URL, json={"name": "Proveedor Nuevo"}, headers=headers_auth)

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["name"] == "Proveedor Nuevo"
    assert isinstance(cuerpo["id"], int)


def test_crear_supplier_sin_token(client):
    respuesta = client.post(URL, json={"name": "Proveedor Nuevo"})

    assert respuesta.status_code == 401


def test_crear_supplier_nombre_vacio(client, headers_auth):
    respuesta = client.post(URL, json={"name": ""}, headers=headers_auth)

    assert respuesta.status_code == 422


# --- GET /suppliers ---


def test_listar_suppliers_solo_de_mi_empresa(client, headers_auth, supplier, headers_otra_empresa):
    client.post(URL, json={"name": "Proveedor Ajeno"}, headers=headers_otra_empresa)

    respuesta = client.get(URL, headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == [supplier]


def test_obtener_supplier(client, headers_auth, supplier):
    respuesta = client.get(f"{URL}{supplier['id']}", headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == supplier


def test_obtener_supplier_inexistente(client, headers_auth):
    respuesta = client.get(f"{URL}999999", headers=headers_auth)

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Proveedor no encontrado"


def test_obtener_supplier_de_otra_empresa(client, supplier, headers_otra_empresa):
    respuesta = client.get(f"{URL}{supplier['id']}", headers=headers_otra_empresa)

    assert respuesta.status_code == 404


@pytest.mark.parametrize("metodo", ["get", "put", "patch", "delete"])
def test_supplier_id_fuera_de_rango(client, headers_auth, metodo):
    kwargs = {"json": {"name": "X"}} if metodo in ("put", "patch") else {}

    respuesta = getattr(client, metodo)(f"{URL}99999999999", headers=headers_auth, **kwargs)

    assert respuesta.status_code == 422


# --- PUT / PATCH /suppliers/{id} ---


def test_actualizar_supplier(client, headers_auth, supplier):
    respuesta = client.put(f"{URL}{supplier['id']}", json={"name": "Renombrado"}, headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == {"id": supplier["id"], "name": "Renombrado"}


def test_actualizar_supplier_falta_campo(client, headers_auth, supplier):
    respuesta = client.put(f"{URL}{supplier['id']}", json={}, headers=headers_auth)

    assert respuesta.status_code == 422


def test_patch_supplier(client, headers_auth, supplier):
    respuesta = client.patch(f"{URL}{supplier['id']}", json={"name": "Editado"}, headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json()["name"] == "Editado"


def test_patch_supplier_body_vacio(client, headers_auth, supplier):
    respuesta = client.patch(f"{URL}{supplier['id']}", json={}, headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == supplier


def test_patch_supplier_de_otra_empresa(client, headers_auth, supplier, headers_otra_empresa):
    respuesta = client.patch(
        f"{URL}{supplier['id']}", json={"name": "Hackeado"}, headers=headers_otra_empresa
    )

    assert respuesta.status_code == 404
    assert client.get(f"{URL}{supplier['id']}", headers=headers_auth).json() == supplier


# --- DELETE /suppliers/{id} ---


def test_eliminar_supplier(client, headers_auth, supplier):
    respuesta = client.delete(f"{URL}{supplier['id']}", headers=headers_auth)

    assert respuesta.status_code == 204
    assert client.get(f"{URL}{supplier['id']}", headers=headers_auth).status_code == 404


def test_eliminar_supplier_con_productos(client, headers_auth, supplier, product):
    respuesta = client.delete(f"{URL}{supplier['id']}", headers=headers_auth)

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "El proveedor tiene productos asociados"
    assert client.get(f"{URL}{supplier['id']}", headers=headers_auth).status_code == 200


def test_eliminar_supplier_de_otra_empresa(client, headers_auth, supplier, headers_otra_empresa):
    respuesta = client.delete(f"{URL}{supplier['id']}", headers=headers_otra_empresa)

    assert respuesta.status_code == 404
    assert client.get(f"{URL}{supplier['id']}", headers=headers_auth).status_code == 200


def test_eliminar_supplier_carrera_con_nuevo_producto(
    client, headers_auth, supplier, product, monkeypatch
):
    """Simula que el producto se creó entre la verificación y el commit."""
    monkeypatch.setattr(crud_supplier, "_tiene_productos", lambda db, supplier_id: False)

    respuesta = client.delete(f"{URL}{supplier['id']}", headers=headers_auth)

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "El proveedor tiene productos asociados"
    assert client.get(f"{URL}{supplier['id']}", headers=headers_auth).status_code == 200
