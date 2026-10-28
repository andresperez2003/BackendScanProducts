from datetime import UTC, datetime, timedelta

from app.models.intento_login import IntentoLogin
from app.security import crear_token
from tests.conftest import headers_de

LOGIN = "/auth/login"
ME = "/auth/me"
CAMBIAR = "/auth/cambiar-contrasena"
MENSAJE_CREDENCIALES = "Usuario o contraseña incorrectos"


def _login(client, usuario, contrasena):
    return client.post(LOGIN, data={"username": usuario, "password": contrasena})


# --- POST /auth/login ---


def test_login_correcto(client, empresa_existente):
    respuesta = _login(client, "empresa_uno", "secreta123")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["access_token"]


def test_login_token_sirve_para_me(client, empresa_existente):
    token = _login(client, "empresa_uno", "secreta123").json()["access_token"]

    respuesta = client.get(ME, headers={"Authorization": f"Bearer {token}"})

    assert respuesta.status_code == 200
    assert respuesta.json() == empresa_existente


def test_login_contrasena_incorrecta(client, empresa_existente):
    respuesta = _login(client, "empresa_uno", "incorrecta")

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == MENSAJE_CREDENCIALES
    assert respuesta.headers["WWW-Authenticate"] == "Bearer"


def test_login_usuario_inexistente(client):
    respuesta = _login(client, "no_existe", "secreta123")

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == MENSAJE_CREDENCIALES


def test_login_falta_campo(client):
    respuesta = client.post(LOGIN, data={"username": "empresa_uno"})

    assert respuesta.status_code == 422


def test_login_usuario_muy_largo(client):
    respuesta = _login(client, "u" * 51, "secreta123")

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == MENSAJE_CREDENCIALES


def test_login_contrasena_muy_larga(client, empresa_existente):
    respuesta = _login(client, "empresa_uno", "a" * 129)

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == MENSAJE_CREDENCIALES


# --- Bloqueo por intentos fallidos ---


def _fallar(client, usuario, veces):
    for _ in range(veces):
        _login(client, usuario, "incorrecta")


def test_login_4_fallos_no_bloquea(client, empresa_existente):
    _fallar(client, "empresa_uno", 4)

    assert _login(client, "empresa_uno", "secreta123").status_code == 200


def test_login_5_fallos_bloquea(client, empresa_existente):
    _fallar(client, "empresa_uno", 4)

    respuesta = _login(client, "empresa_uno", "incorrecta")

    assert respuesta.status_code == 429
    assert "10 minuto" in respuesta.json()["detail"]
    assert 590 <= int(respuesta.headers["Retry-After"]) <= 600


def test_login_bloqueado_rechaza_contrasena_correcta(client, empresa_existente):
    _fallar(client, "empresa_uno", 5)

    respuesta = _login(client, "empresa_uno", "secreta123")

    assert respuesta.status_code == 429


def test_login_desbloqueo_tras_10_minutos(client, db, empresa_existente):
    _fallar(client, "empresa_uno", 5)
    # Simula que pasaron los 10 minutos.
    db.get(IntentoLogin, "empresa_uno").bloqueado_hasta = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    assert _login(client, "empresa_uno", "secreta123").status_code == 200


def _envejecer_fallos(db, usuario, minutos):
    """Simula que el último fallo fue hace `minutos` minutos."""
    db.get(IntentoLogin, usuario).ultimo_fallo = datetime.now(UTC) - timedelta(minutes=minutos)
    db.commit()


def test_login_fallos_de_hace_mas_de_10_minutos_no_cuentan(client, db, empresa_existente):
    _fallar(client, "empresa_uno", 4)
    _envejecer_fallos(db, "empresa_uno", 11)

    # Si los 4 viejos contaran, este sería el 5º y bloquearía.
    respuesta = _login(client, "empresa_uno", "incorrecta")

    assert respuesta.status_code == 401
    db.expire_all()
    assert db.get(IntentoLogin, "empresa_uno").fallidos == 1


def test_login_fallos_recientes_si_cuentan(client, db, empresa_existente):
    _fallar(client, "empresa_uno", 4)
    _envejecer_fallos(db, "empresa_uno", 9)

    assert _login(client, "empresa_uno", "incorrecta").status_code == 429


def test_intentos_viejos_se_borran(client, db):
    """Los usuarios inventados no dejan filas para siempre."""
    _fallar(client, "inventado", 1)
    _envejecer_fallos(db, "inventado", 11)

    _fallar(client, "otro_inventado", 1)

    db.expire_all()
    assert db.get(IntentoLogin, "inventado") is None
    assert db.get(IntentoLogin, "otro_inventado") is not None


def test_bloqueo_activo_no_se_borra(client, db):
    _fallar(client, "bloqueado", 5)
    _envejecer_fallos(db, "bloqueado", 11)

    _fallar(client, "otro_usuario", 1)

    db.expire_all()
    assert db.get(IntentoLogin, "bloqueado") is not None
    assert _login(client, "bloqueado", "incorrecta").status_code == 429


def test_login_tras_desbloqueo_hay_5_intentos_nuevos(client, db, empresa_existente):
    _fallar(client, "empresa_uno", 5)
    db.get(IntentoLogin, "empresa_uno").bloqueado_hasta = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    _fallar(client, "empresa_uno", 4)

    assert _login(client, "empresa_uno", "secreta123").status_code == 200


def test_login_exito_reinicia_contador(client, empresa_existente):
    _fallar(client, "empresa_uno", 4)
    _login(client, "empresa_uno", "secreta123")
    _fallar(client, "empresa_uno", 4)

    assert _login(client, "empresa_uno", "secreta123").status_code == 200


def test_login_bloqueo_no_afecta_a_otros_usuarios(client, empresa_existente, headers_otra_empresa):
    _fallar(client, "empresa_uno", 5)

    assert _login(client, "empresa_ajena", "clave1234").status_code == 200


def test_login_usuario_inexistente_tambien_se_bloquea(client):
    """Igual que un usuario real: el bloqueo no revela qué usuarios existen."""
    _fallar(client, "no_existe", 4)

    respuesta = _login(client, "no_existe", "incorrecta")

    assert respuesta.status_code == 429


def test_cambiar_usuario_mantiene_bloqueo(client, db, empresa_existente, headers_auth):
    _fallar(client, "empresa_uno", 5)

    client.patch(
        f"/empresas/{empresa_existente['id']}",
        json={"usuario": "nuevo_nombre"},
        headers=headers_auth,
    )

    assert _login(client, "nuevo_nombre", "secreta123").status_code == 429


# --- POST /auth/cambiar-contrasena ---


def _cambiar(client, headers, actual, nueva):
    return client.post(
        CAMBIAR,
        json={"contrasena_actual": actual, "contrasena_nueva": nueva},
        headers=headers,
    )


def test_cambiar_contrasena(client, empresa_existente, headers_auth):
    respuesta = _cambiar(client, headers_auth, "secreta123", "nueva12345")

    assert respuesta.status_code == 200
    assert _login(client, "empresa_uno", "secreta123").status_code == 401
    assert _login(client, "empresa_uno", "nueva12345").status_code == 200


def test_cambiar_contrasena_invalida_tokens_anteriores(client, empresa_existente, headers_auth):
    """Si alguien robó el token, deja de servirle al cambiar la contraseña."""
    token_robado = _login(client, "empresa_uno", "secreta123").json()["access_token"]

    _cambiar(client, headers_auth, "secreta123", "nueva12345")

    assert client.get(ME, headers={"Authorization": f"Bearer {token_robado}"}).status_code == 401
    assert client.get(ME, headers=headers_auth).status_code == 401


def test_cambiar_contrasena_devuelve_token_nuevo(client, empresa_existente, headers_auth):
    token = _cambiar(client, headers_auth, "secreta123", "nueva12345").json()["access_token"]

    respuesta = client.get(ME, headers={"Authorization": f"Bearer {token}"})

    assert respuesta.status_code == 200
    assert respuesta.json() == empresa_existente


def test_cambiar_contrasena_fallida_no_invalida_tokens(client, empresa_existente, headers_auth):
    _cambiar(client, headers_auth, "incorrecta", "nueva12345")

    assert client.get(ME, headers=headers_auth).status_code == 200


def test_cambiar_contrasena_actual_incorrecta(client, empresa_existente, headers_auth):
    respuesta = _cambiar(client, headers_auth, "incorrecta", "nueva12345")

    assert respuesta.status_code == 400
    assert respuesta.json()["detail"] == "La contraseña actual es incorrecta"
    assert _login(client, "empresa_uno", "secreta123").status_code == 200


def test_cambiar_contrasena_sin_token(client):
    respuesta = _cambiar(client, {}, "secreta123", "nueva12345")

    assert respuesta.status_code == 401


def test_cambiar_contrasena_nueva_muy_corta(client, empresa_existente, headers_auth):
    respuesta = _cambiar(client, headers_auth, "secreta123", "a" * 7)

    assert respuesta.status_code == 422
    assert _login(client, "empresa_uno", "secreta123").status_code == 200


def test_cambiar_contrasena_nueva_muy_larga(client, empresa_existente, headers_auth):
    respuesta = _cambiar(client, headers_auth, "secreta123", "a" * 129)

    assert respuesta.status_code == 422


def test_cambiar_contrasena_fallos_bloquean_login(client, empresa_existente, headers_auth):
    """Con un token robado no se puede adivinar la contraseña actual sin límite."""
    for _ in range(4):
        assert _cambiar(client, headers_auth, "incorrecta", "nueva12345").status_code == 400

    assert _cambiar(client, headers_auth, "incorrecta", "nueva12345").status_code == 429
    assert _cambiar(client, headers_auth, "secreta123", "nueva12345").status_code == 429
    assert _login(client, "empresa_uno", "secreta123").status_code == 429


# --- GET /auth/me ---


def test_me_con_token(client, empresa_existente, headers_auth):
    respuesta = client.get(ME, headers=headers_auth)

    assert respuesta.status_code == 200
    assert respuesta.json() == empresa_existente


def test_me_sin_token(client):
    respuesta = client.get(ME)

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == "No autenticado"


def test_me_token_invalido(client):
    respuesta = client.get(ME, headers={"Authorization": "Bearer abc123"})

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == "Token inválido o expirado"


def test_me_token_expirado(client, empresa_existente):
    token = crear_token(empresa_existente["id"], 0, expira_en=timedelta(seconds=-1))

    respuesta = client.get(ME, headers={"Authorization": f"Bearer {token}"})

    assert respuesta.status_code == 401


def test_me_empresa_eliminada(client, empresa_existente, headers_auth):
    client.delete(f"/empresas/{empresa_existente['id']}", headers=headers_auth)

    respuesta = client.get(ME, headers=headers_de(empresa_existente["id"]))

    assert respuesta.status_code == 401
