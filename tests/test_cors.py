ORIGEN = "http://localhost:5173"


def test_preflight_desde_el_frontend(client):
    respuesta = client.options(
        "/products/",
        headers={
            "Origin": ORIGEN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.headers["access-control-allow-origin"] == ORIGEN
    assert "POST" in respuesta.headers["access-control-allow-methods"]
    assert "authorization" in respuesta.headers["access-control-allow-headers"].lower()


def test_origen_no_permitido(client):
    respuesta = client.options(
        "/products/",
        headers={"Origin": "http://sitio-malicioso.com", "Access-Control-Request-Method": "GET"},
    )

    assert "access-control-allow-origin" not in respuesta.headers


def test_retry_after_es_visible_para_el_frontend(client):
    for _ in range(5):
        respuesta = client.post(
            "/auth/login",
            data={"username": "no_existe", "password": "incorrecta"},
            headers={"Origin": ORIGEN},
        )

    assert respuesta.status_code == 429
    assert respuesta.headers["access-control-allow-origin"] == ORIGEN
    assert "retry-after" in respuesta.headers["access-control-expose-headers"].lower()
