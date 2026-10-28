from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.crud import product as crud_product
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.tracking import Tracking

URL = "/products/"


def _datos(supplier_id, **cambios):
    return {"name": "Queso", "unit": "kg", "supplier_id": supplier_id} | cambios


# --- POST /products ---


def test_crear_product(client, headers_auth, supplier):
    respuesta = client.post(URL, json=_datos(supplier["id"]), headers=headers_auth)

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert isinstance(cuerpo["id"], int)
    assert cuerpo | {"id": None, "created_at": None} == _datos(supplier["id"]) | {
        "id": None,
        "created_at": None,
    }


def test_crear_product_ya_no_tiene_lote_fecha_ni_cantidad(client, headers_auth, supplier):
    """Lote y fecha viven en el seguimiento y la cantidad ya no existe: se ignoran aquí."""
    datos = _datos(supplier["id"]) | {"batch": "X-1", "due_date": "2027-01-01", "quantity": 5}

    cuerpo = client.post(URL, json=datos, headers=headers_auth).json()

    assert "batch" not in cuerpo
    assert "due_date" not in cuerpo
    assert "quantity" not in cuerpo
    assert "total_quantity" not in cuerpo


def test_crear_product_sin_token(client, supplier):
    respuesta = client.post(URL, json=_datos(supplier["id"]))

    assert respuesta.status_code == 401


def test_crear_product_supplier_inexistente(client, headers_auth):
    respuesta = client.post(URL, json=_datos(999999), headers=headers_auth)

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Proveedor no encontrado"


def test_crear_product_supplier_de_otra_empresa(client, supplier, headers_otra_empresa):
    respuesta = client.post(URL, json=_datos(supplier["id"]), headers=headers_otra_empresa)

    assert respuesta.status_code == 404


def test_crear_product_falta_campo(client, headers_auth, supplier):
    datos = _datos(supplier["id"])
    del datos["unit"]

    respuesta = client.post(URL, json=datos, headers=headers_auth)

    assert respuesta.status_code == 422


# --- GET /products ---


def test_listar_products_solo_de_mi_empresa(client, headers_auth, product, headers_otra_empresa):
    otro_supplier = client.post(
        "/suppliers/", json={"name": "Ajeno"}, headers=headers_otra_empresa
    ).json()
    client.post(URL, json=_datos(otro_supplier["id"]), headers=headers_otra_empresa)

    respuesta = client.get(URL, headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == [product]


def test_listar_products_por_supplier(client, headers_auth, supplier, product):
    otro_supplier = client.post("/suppliers/", json={"name": "Otro"}, headers=headers_auth).json()
    client.post(URL, json=_datos(otro_supplier["id"]), headers=headers_auth)

    respuesta = client.get(URL, params={"supplier_id": supplier["id"]}, headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == [product]


def test_obtener_product(client, headers_auth, product):
    respuesta = client.get(f"{URL}{product['id']}", headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == product


def test_obtener_product_inexistente(client, headers_auth):
    respuesta = client.get(f"{URL}999999", headers=headers_auth)

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Producto no encontrado"


def test_obtener_product_de_otra_empresa(client, product, headers_otra_empresa):
    respuesta = client.get(f"{URL}{product['id']}", headers=headers_otra_empresa)

    assert respuesta.status_code == 404


@pytest.mark.parametrize("metodo", ["get", "patch", "delete"])
def test_product_id_fuera_de_rango(client, headers_auth, metodo):
    kwargs = {"json": {"name": "X"}} if metodo == "patch" else {}

    respuesta = getattr(client, metodo)(f"{URL}99999999999", headers=headers_auth, **kwargs)

    assert respuesta.status_code == 422


def test_listar_products_supplier_id_fuera_de_rango(client, headers_auth):
    respuesta = client.get(f"{URL}?supplier_id=99999999999", headers=headers_auth)

    assert respuesta.status_code == 422


def test_crear_product_supplier_id_fuera_de_rango(client, headers_auth):
    respuesta = client.post(URL, json=_datos(99999999999), headers=headers_auth)

    assert respuesta.status_code == 422


def test_crear_product_carrera_supplier_eliminado(client, headers_auth, monkeypatch):
    """Simula que el proveedor se eliminó entre la validación y el commit."""
    monkeypatch.setattr(crud_product.crud_supplier, "obtener", lambda *args: None)

    respuesta = client.post(URL, json=_datos(999999), headers=headers_auth)

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Proveedor no encontrado"


# --- PUT /products/{id} ---


def test_actualizar_product(client, headers_auth, supplier, product):
    nuevos = _datos(supplier["id"], name="Yogur", unit="unidad")

    respuesta = client.put(f"{URL}{product['id']}", json=nuevos, headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == nuevos | {
        "id": product["id"],
        "created_at": product["created_at"],
    }


def test_actualizar_product_falta_campo(client, headers_auth, product):
    respuesta = client.put(f"{URL}{product['id']}", json={"name": "Solo nombre"}, headers=headers_auth)

    assert respuesta.status_code == 422


# --- PATCH /products/{id} ---


def test_patch_product_unit(client, headers_auth, product):
    respuesta = client.patch(f"{URL}{product['id']}", json={"unit": "ml"}, headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == product | {"unit": "ml"}


def test_patch_product_null_en_obligatorio(client, headers_auth, product):
    respuesta = client.patch(f"{URL}{product['id']}", json={"name": None}, headers=headers_auth)

    assert respuesta.status_code == 422


def test_patch_product_cambiar_supplier(client, headers_auth, product):
    otro = client.post("/suppliers/", json={"name": "Otro"}, headers=headers_auth).json()

    respuesta = client.patch(
        f"{URL}{product['id']}", json={"supplier_id": otro["id"]}, headers=headers_auth
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["supplier_id"] == otro["id"]


def test_patch_product_supplier_de_otra_empresa(client, headers_auth, product, headers_otra_empresa):
    ajeno = client.post("/suppliers/", json={"name": "Ajeno"}, headers=headers_otra_empresa).json()

    respuesta = client.patch(
        f"{URL}{product['id']}", json={"supplier_id": ajeno["id"]}, headers=headers_auth
    )

    assert respuesta.status_code == 404
    assert client.get(f"{URL}{product['id']}", headers=headers_auth).json() == product


def test_patch_product_de_otra_empresa(client, headers_auth, product, headers_otra_empresa):
    respuesta = client.patch(
        f"{URL}{product['id']}", json={"name": "Hackeado"}, headers=headers_otra_empresa
    )

    assert respuesta.status_code == 404
    assert client.get(f"{URL}{product['id']}", headers=headers_auth).json() == product


# --- DELETE /products/{id} ---


def test_eliminar_product(client, headers_auth, supplier, product):
    respuesta = client.delete(f"{URL}{product['id']}", headers=headers_auth)

    assert respuesta.status_code == 204
    assert client.get(f"{URL}{product['id']}", headers=headers_auth).status_code == 404
    # Sin productos, el proveedor ya se puede eliminar
    assert client.delete(f"/suppliers/{supplier['id']}", headers=headers_auth).status_code == 204


def test_eliminar_product_con_seguimientos(client, headers_auth, product, tracking):
    respuesta = client.delete(f"{URL}{product['id']}", headers=headers_auth)

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "El producto tiene seguimientos asociados"
    assert client.get(f"{URL}{product['id']}", headers=headers_auth).status_code == 200


def test_eliminar_product_tras_borrar_sus_seguimientos(client, headers_auth, product, tracking):
    client.delete(f"/trackings/{tracking['id']}", headers=headers_auth)

    assert client.delete(f"{URL}{product['id']}", headers=headers_auth).status_code == 204


def test_eliminar_product_carrera_con_nuevo_seguimiento(
    client, headers_auth, product, tracking, monkeypatch
):
    """Simula que el seguimiento se creó entre la verificación y el commit."""
    monkeypatch.setattr(crud_product, "_tiene_seguimientos", lambda db, product_id: False)

    respuesta = client.delete(f"{URL}{product['id']}", headers=headers_auth)

    assert respuesta.status_code == 409
    assert client.get(f"{URL}{product['id']}", headers=headers_auth).status_code == 200


def test_eliminar_product_de_otra_empresa(client, headers_auth, product, headers_otra_empresa):
    respuesta = client.delete(f"{URL}{product['id']}", headers=headers_otra_empresa)

    assert respuesta.status_code == 404
    assert client.get(f"{URL}{product['id']}", headers=headers_auth).status_code == 200


# --- Eliminar la empresa ---


def test_eliminar_empresa_borra_sus_suppliers_products_y_trackings(
    client, db, empresa_existente, headers_auth, tracking
):
    respuesta = client.delete(f"/empresas/{empresa_existente['id']}", headers=headers_auth)

    assert respuesta.status_code == 204
    db.expire_all()
    assert db.scalars(select(Supplier)).all() == []
    assert db.scalars(select(Product)).all() == []
    assert db.scalars(select(Tracking)).all() == []


# --- created_at ---


def test_crear_product_devuelve_created_at(client, headers_auth, supplier):
    antes = datetime.now(UTC)

    cuerpo = client.post(URL, json=_datos(supplier["id"]), headers=headers_auth).json()

    creado = datetime.fromisoformat(cuerpo["created_at"])
    assert abs(creado - antes) < timedelta(minutes=1)


def test_created_at_no_lo_puede_poner_el_cliente(client, headers_auth, supplier):
    datos = _datos(supplier["id"]) | {"created_at": "2000-01-01T00:00:00Z"}

    cuerpo = client.post(URL, json=datos, headers=headers_auth).json()

    assert not cuerpo["created_at"].startswith("2000")


def test_actualizar_product_no_cambia_created_at(client, headers_auth, supplier, product):
    respuesta = client.put(
        f"{URL}{product['id']}",
        json=_datos(supplier["id"]) | {"created_at": "2000-01-01T00:00:00Z"},
        headers=headers_auth,
    )

    assert respuesta.json()["created_at"] == product["created_at"]
