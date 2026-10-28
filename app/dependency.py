from collections.abc import Generator

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.crud import administrador as crud_admin
from app.crud import empresa as crud_empresa
from app.database import SessionLocal
from app.exceptions import TokenInvalido
from app.models.administrador import Administrador
from app.models.empresa import Empresa
from app.security import decodificar_token

# auto_error=False para responder con nuestro TokenInvalido (en español)
# en vez del 401 "Not authenticated" de FastAPI.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
oauth2_scheme_admin = OAuth2PasswordBearer(
    tokenUrl="/admin/auth/login", scheme_name="Administrador", auto_error=False
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_empresa_actual(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Empresa:
    if token is None:
        raise TokenInvalido("No autenticado")
    empresa_id, version_token = decodificar_token(token)
    empresa = crud_empresa.obtener(db, empresa_id)
    # Versión distinta: el token es de antes del último cambio de contraseña.
    if empresa is None or empresa.version_token != version_token:
        raise TokenInvalido()
    return empresa


def get_admin_actual(
    token: str | None = Depends(oauth2_scheme_admin), db: Session = Depends(get_db)
) -> Administrador:
    """Solo acepta tokens de administrador: uno de empresa recibe 401."""
    if token is None:
        raise TokenInvalido("No autenticado")
    admin_id, version_token = decodificar_token(token, tipo="admin")
    admin = crud_admin.obtener(db, admin_id)
    if admin is None or admin.version_token != version_token:
        raise TokenInvalido()
    return admin
