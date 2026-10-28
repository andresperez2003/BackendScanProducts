import pytest

from app.crud import tracking as crud_tracking

URL = "/trackings/"


def _datos(product_id, **cambios):
    datos = {"batch": "Q-100", "due_date": "2027-01-15", "product_id": product_id}
    return datos | cambios


def _crear_producto(client, headers, supplier_id, name="Queso"):
    respuesta = client.post(
        "/products/", json={"name": name, "unit": "kg", "supplier_id": supplier_id}, headers=headers
    )
    assert respuesta.status_code == 201
    return respuesta.json()


# --- POST /trackings ---


def test_crear_tracking(client, headers_auth, product, supplier):
    respuesta = client.post(URL, json=_datos(product["id"]), headers=headers_auth)

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert isinstance(cuerpo["id"], int)
    assert cuerpo["batch"] == "Q-100"
    assert cuerpo["due_date"] == "2027-01-15"
    assert cuerpo["product_id"] == product["id"]


def test_crear_tracking_trae_producto_y_proveedor(client, headers_auth, product, supplier):
    cuerpo = client.post(URL, json=_datos(product["id"]), headers=headers_auth).json()

    assert cuerpo["product"] == {"id": product["id"], "name": "Leche", "unit": "l"}
    assert cuerpo["supplier"] == supplier


def test_crear_tracking_sin_due_date(client, headers_auth, product):
    datos = _datos(product["id"])
    del datos["due_date"]

    respuesta = client.post(URL, json=datos, headers=headers_auth)

    assert respuesta.status_code == 201
    assert respuesta.json()["due_date"] is None


def test_crear_tracking_sin_token(client, product):
    assert client.post(URL, json=_datos(product["id"])).status_code == 401


def test_crear_tracking_producto_inexistente(client, headers_auth):
    respuesta = client.post(URL, json=_datos(999999), headers=headers_auth)

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Producto no encontrado"


def test_crear_tracking_producto_de_otra_empresa(client, product, headers_otra_empresa):
    respuesta = client.post(URL, json=_datos(product["id"]), headers=headers_otra_empresa)

    assert respuesta.status_code == 404


@pytest.mark.parametrize(
    "cambio",
    [
        {"batch": ""},
        {"batch": "x" * 51},
        {"due_date": "31/12/2026"},
        {"product_id": 99999999999},
    ],
)
def test_crear_tracking_datos_invalidos(client, headers_auth, product, cambio):
    respuesta = client.post(URL, json=_datos(product["id"]) | cambio, headers=headers_auth)

    assert respuesta.status_code == 422


@pytest.mark.parametrize("campo", ["batch", "product_id"])
def test_crear_tracking_falta_campo(client, headers_auth, product, campo):
    datos = _datos(product["id"])
    del datos[campo]

    assert client.post(URL, json=datos, headers=headers_auth).status_code == 422


def test_crear_tracking_ya_no_tiene_cantidad(client, headers_auth, product):
    """La cantidad se quitó del seguimiento: si llega, se ignora."""
    cuerpo = client.post(URL, json=_datos(product["id"]) | {"quantity": 5}, headers=headers_auth).json()

    assert "quantity" not in cuerpo


def test_crear_tracking_lote_duplicado(client, headers_auth, product, tracking):
    respuesta = client.post(URL, json=_datos(product["id"], batch="L-001"), headers=headers_auth)

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "El lote 'L-001' ya existe para este producto"


def test_mismo_lote_en_otro_producto_si_se_permite(client, headers_auth, supplier, tracking):
    otro = _crear_producto(client, headers_auth, supplier["id"])

    respuesta = client.post(URL, json=_datos(otro["id"], batch="L-001"), headers=headers_auth)

    assert respuesta.status_code == 201


def test_crear_tracking_carrera_producto_eliminado(client, headers_auth, monkeypatch):
    """Simula que el producto se eliminó entre la validación y el commit."""
    monkeypatch.setattr(crud_tracking.crud_product, "obtener", lambda *args: None)

    respuesta = client.post(URL, json=_datos(999999), headers=headers_auth)

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Producto no encontrado"


# --- GET /trackings ---


def test_listar_trackings_solo_de_mi_empresa(client, headers_auth, tracking, headers_otra_empresa):
    ajeno = client.post("/suppliers/", json={"name": "Ajeno"}, headers=headers_otra_empresa).json()
    producto_ajeno = _crear_producto(client, headers_otra_empresa, ajeno["id"])
    client.post(URL, json=_datos(producto_ajeno["id"]), headers=headers_otra_empresa)

    respuesta = client.get(URL, headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == [tracking]


def test_listar_trackings_ordenados_por_vencimiento(client, headers_auth, product):
    for batch, fecha in [("C", None), ("B", "2027-03-01"), ("A", "2026-11-01")]:
        client.post(URL, json=_datos(product["id"], batch=batch, due_date=fecha), headers=headers_auth)

    lotes = [t["batch"] for t in client.get(URL, headers=headers_auth).json()]

    assert lotes == ["A", "B", "C"]


def test_listar_trackings_por_producto(client, headers_auth, supplier, tracking):
    otro = _crear_producto(client, headers_auth, supplier["id"])
    client.post(URL, json=_datos(otro["id"]), headers=headers_auth)

    respuesta = client.get(URL, params={"product_id": tracking["product_id"]}, headers=headers_auth)

    assert respuesta.json() == [tracking]


def test_listar_trackings_por_proveedor(client, headers_auth, tracking, supplier):
    otro_supplier = client.post("/suppliers/", json={"name": "Otro"}, headers=headers_auth).json()
    otro = _crear_producto(client, headers_auth, otro_supplier["id"])
    client.post(URL, json=_datos(otro["id"]), headers=headers_auth)

    respuesta = client.get(URL, params={"supplier_id": supplier["id"]}, headers=headers_auth)

    assert respuesta.json() == [tracking]


def test_listar_trackings_sin_token(client):
    assert client.get(URL).status_code == 401


def test_obtener_tracking(client, headers_auth, tracking):
    respuesta = client.get(f"{URL}{tracking['id']}", headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == tracking


def test_obtener_tracking_inexistente(client, headers_auth):
    respuesta = client.get(f"{URL}999999", headers=headers_auth)

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Seguimiento no encontrado"


def test_obtener_tracking_de_otra_empresa(client, tracking, headers_otra_empresa):
    assert client.get(f"{URL}{tracking['id']}", headers=headers_otra_empresa).status_code == 404


@pytest.mark.parametrize("metodo", ["get", "put", "patch", "delete"])
def test_tracking_id_fuera_de_rango(client, headers_auth, product, metodo):
    kwargs = {"json": _datos(product["id"])} if metodo in ("put", "patch") else {}

    respuesta = getattr(client, metodo)(f"{URL}99999999999", headers=headers_auth, **kwargs)

    assert respuesta.status_code == 422


# --- PUT /trackings/{id} ---


def test_actualizar_tracking(client, headers_auth, tracking):
    nuevos = _datos(tracking["product_id"], batch="L-002", due_date=None)

    respuesta = client.put(f"{URL}{tracking['id']}", json=nuevos, headers=headers_auth)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert (cuerpo["batch"], cuerpo["due_date"]) == ("L-002", None)
    assert cuerpo["created_at"] == tracking["created_at"]


def test_actualizar_tracking_cambiar_producto(client, headers_auth, supplier, tracking):
    otro = _crear_producto(client, headers_auth, supplier["id"], name="Kumis")

    respuesta = client.put(
        f"{URL}{tracking['id']}", json=_datos(otro["id"], batch="L-001"), headers=headers_auth
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["product"]["name"] == "Kumis"


def test_actualizar_tracking_lote_duplicado(client, headers_auth, product, tracking):
    otro = client.post(URL, json=_datos(product["id"], batch="L-002"), headers=headers_auth).json()

    respuesta = client.put(
        f"{URL}{otro['id']}", json=_datos(product["id"], batch="L-001"), headers=headers_auth
    )

    assert respuesta.status_code == 409
    assert client.get(f"{URL}{otro['id']}", headers=headers_auth).json()["batch"] == "L-002"


def test_actualizar_tracking_falta_campo(client, headers_auth, tracking):
    respuesta = client.put(f"{URL}{tracking['id']}", json={"batch": "X"}, headers=headers_auth)

    assert respuesta.status_code == 422


def test_actualizar_tracking_de_otra_empresa(client, tracking, headers_otra_empresa):
    respuesta = client.put(
        f"{URL}{tracking['id']}", json=_datos(tracking["product_id"]), headers=headers_otra_empresa
    )

    assert respuesta.status_code == 404


# --- PATCH /trackings/{id} ---


def test_patch_tracking_batch(client, headers_auth, tracking):
    respuesta = client.patch(f"{URL}{tracking['id']}", json={"batch": "L-009"}, headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == tracking | {"batch": "L-009"}


def test_patch_tracking_borrar_due_date(client, headers_auth, tracking):
    respuesta = client.patch(f"{URL}{tracking['id']}", json={"due_date": None}, headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == tracking | {"due_date": None}


@pytest.mark.parametrize("campo", ["batch", "product_id"])
def test_patch_tracking_null_en_obligatorio(client, headers_auth, tracking, campo):
    respuesta = client.patch(f"{URL}{tracking['id']}", json={campo: None}, headers=headers_auth)

    assert respuesta.status_code == 422


def test_patch_tracking_producto_de_otra_empresa(client, headers_auth, tracking, headers_otra_empresa):
    ajeno = client.post("/suppliers/", json={"name": "Ajeno"}, headers=headers_otra_empresa).json()
    producto_ajeno = _crear_producto(client, headers_otra_empresa, ajeno["id"])

    respuesta = client.patch(
        f"{URL}{tracking['id']}", json={"product_id": producto_ajeno["id"]}, headers=headers_auth
    )

    assert respuesta.status_code == 404
    assert client.get(f"{URL}{tracking['id']}", headers=headers_auth).json() == tracking


def test_cambiar_proveedor_del_producto_se_ve_en_el_seguimiento(
    client, headers_auth, product, tracking
):
    """El proveedor no se guarda en el seguimiento: siempre es el del producto."""
    nuevo = client.post("/suppliers/", json={"name": "Nuevo"}, headers=headers_auth).json()
    client.patch(f"/products/{product['id']}", json={"supplier_id": nuevo["id"]}, headers=headers_auth)

    respuesta = client.get(f"{URL}{tracking['id']}", headers=headers_auth)

    assert respuesta.json()["supplier"] == nuevo


# --- DELETE /trackings/{id} ---


def test_eliminar_tracking(client, headers_auth, product, tracking):
    respuesta = client.delete(f"{URL}{tracking['id']}", headers=headers_auth)

    assert respuesta.status_code == 204
    assert client.get(f"{URL}{tracking['id']}", headers=headers_auth).status_code == 404


def test_eliminar_tracking_de_otra_empresa(client, headers_auth, tracking, headers_otra_empresa):
    respuesta = client.delete(f"{URL}{tracking['id']}", headers=headers_otra_empresa)

    assert respuesta.status_code == 404
    assert client.get(f"{URL}{tracking['id']}", headers=headers_auth).status_code == 200


def test_eliminar_tracking_sin_token(client, tracking):
    assert client.delete(f"{URL}{tracking['id']}").status_code == 401
