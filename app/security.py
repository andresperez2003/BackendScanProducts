from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.config import get_settings
from app.exceptions import TokenInvalido

ALGORITMO = "HS256"

_password_hash = PasswordHash.recommended()
# Se usa cuando el usuario no existe, para que la respuesta tarde lo mismo
# y no se pueda averiguar qué usuarios existen midiendo el tiempo.
_HASH_FALSO = _password_hash.hash("contrasena-inexistente")


def hashear_contrasena(contrasena: str) -> str:
    return _password_hash.hash(contrasena)


def verificar_contrasena(contrasena: str, contrasena_hash: str | None) -> bool:
    if contrasena_hash is None:
        _password_hash.verify(contrasena, _HASH_FALSO)
        return False
    try:
        return _password_hash.verify(contrasena, contrasena_hash)
    except UnknownHashError:
        return False


TipoToken = Literal["empresa", "admin"]


def crear_token(
    sujeto_id: int,
    version_token: int,
    expira_en: timedelta | None = None,
    tipo: TipoToken = "empresa",
) -> str:
    """Token de una empresa o, con tipo="admin", de un administrador."""
    settings = get_settings()
    if expira_en is None:
        expira_en = timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(sujeto_id),
        "ver": version_token,
        "tipo": tipo,
        "exp": datetime.now(UTC) + expira_en,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITMO)


def decodificar_token(token: str, tipo: TipoToken = "empresa") -> tuple[int, int]:
    """Devuelve (id del sujeto, versión del token), o lanza TokenInvalido.

    Un token de otro tipo también es inválido: el de un administrador no
    sirve en la app de las empresas ni el de una empresa en /admin. Los
    tokens emitidos antes de existir "tipo" son de empresa.
    """
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITMO])
        if payload.get("tipo", "empresa") != tipo:
            raise TokenInvalido()
        return int(payload["sub"]), int(payload["ver"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise TokenInvalido() from None
