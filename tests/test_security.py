from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import get_settings
from app.exceptions import TokenInvalido
from app.security import (
    ALGORITMO,
    crear_token,
    decodificar_token,
    hashear_contrasena,
    verificar_contrasena,
)


def test_crear_y_decodificar_token():
    token = crear_token(5, 3)

    assert decodificar_token(token) == (5, 3)


def test_token_sin_version():
    """Los tokens emitidos antes de version_token no traen "ver"."""
    payload = {"sub": "5", "exp": datetime.now(UTC) + timedelta(minutes=5)}
    token = jwt.encode(payload, get_settings().secret_key, algorithm=ALGORITMO)

    with pytest.raises(TokenInvalido):
        decodificar_token(token)


def test_token_expirado():
    token = crear_token(5, 0, expira_en=timedelta(seconds=-1))

    with pytest.raises(TokenInvalido):
        decodificar_token(token)


def test_token_firma_invalida():
    payload = {"sub": "5", "exp": datetime.now(UTC) + timedelta(minutes=5)}
    token = jwt.encode(payload, "otra-clave-secreta-" * 4, algorithm=ALGORITMO)

    with pytest.raises(TokenInvalido):
        decodificar_token(token)


def test_verificar_contrasena_correcta_e_incorrecta():
    contrasena_hash = hashear_contrasena("secreta")

    assert verificar_contrasena("secreta", contrasena_hash)
    assert not verificar_contrasena("otra", contrasena_hash)


def test_verificar_contrasena_sin_hash():
    assert not verificar_contrasena("secreta", None)


def test_verificar_contrasena_texto_plano():
    assert not verificar_contrasena("secreta", "secreta")


def test_token_de_admin():
    token = crear_token(5, 2, tipo="admin")

    assert decodificar_token(token, tipo="admin") == (5, 2)
    with pytest.raises(TokenInvalido):
        decodificar_token(token)  # no sirve como token de empresa


def test_token_de_empresa_no_sirve_como_admin():
    with pytest.raises(TokenInvalido):
        decodificar_token(crear_token(5, 0), tipo="admin")


def test_token_sin_tipo_es_de_empresa():
    """Los tokens emitidos antes de existir "tipo" siguen siendo de empresa."""
    payload = {"sub": "5", "ver": 0, "exp": datetime.now(UTC) + timedelta(minutes=5)}
    token = jwt.encode(payload, get_settings().secret_key, algorithm=ALGORITMO)

    assert decodificar_token(token) == (5, 0)
    with pytest.raises(TokenInvalido):
        decodificar_token(token, tipo="admin")
