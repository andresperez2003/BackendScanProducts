from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import intento_login as crud_intentos
from app.crud import plan as crud_plan
from app.exceptions import (
    ContrasenaActualIncorrecta,
    CredencialesInvalidas,
    UsuarioYaExiste,
)
from app.models.empresa import Empresa
from app.schemas.empresa import (
    CONTRASENA_MAX,
    USUARIO_MAX,
    EmpresaCreate,
    EmpresaPatch,
    EmpresaUpdate,
)
from app.security import hashear_contrasena, verificar_contrasena


def crear(db: Session, datos: EmpresaCreate) -> Empresa:
    empresa = Empresa(**_preparar(datos.model_dump()))
    # Toda empresa nueva empieza en la demo para probar la lectura de fotos.
    crud_plan.asignar_demo(db, empresa)
    db.add(empresa)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise UsuarioYaExiste(datos.usuario) from None
    db.refresh(empresa)
    return empresa


def obtener(db: Session, empresa_id: int) -> Empresa | None:
    return db.get(Empresa, empresa_id)


def obtener_por_usuario(db: Session, usuario: str) -> Empresa | None:
    return db.scalar(select(Empresa).where(Empresa.usuario == usuario))


def autenticar(db: Session, usuario: str, contrasena: str) -> Empresa:
    if len(usuario) > USUARIO_MAX or len(contrasena) > CONTRASENA_MAX:
        # Ningún usuario válido puede ser así de largo: se rechaza sin hashear
        # y sin registrar el intento (no entraría en la columna).
        raise CredencialesInvalidas()

    crud_intentos.verificar_no_bloqueado(db, usuario)
    empresa = obtener_por_usuario(db, usuario)
    contrasena_hash = empresa.contrasena if empresa else None
    if not verificar_contrasena(contrasena, contrasena_hash):
        crud_intentos.registrar_fallo(db, usuario)
        raise CredencialesInvalidas()
    crud_intentos.limpiar(db, usuario)
    return empresa


def cambiar_contrasena(
    db: Session, empresa: Empresa, contrasena_actual: str, contrasena_nueva: str
) -> None:
    """Los fallos cuentan para el mismo bloqueo que el login: con un token
    robado no se puede adivinar la contraseña actual sin límite."""
    crud_intentos.verificar_no_bloqueado(db, empresa.usuario)
    if not verificar_contrasena(contrasena_actual, empresa.contrasena):
        crud_intentos.registrar_fallo(db, empresa.usuario)
        raise ContrasenaActualIncorrecta()
    crud_intentos.limpiar(db, empresa.usuario)
    empresa.contrasena = hashear_contrasena(contrasena_nueva)
    # Invalida todos los tokens anteriores, incluido uno que pudiera estar robado.
    empresa.version_token += 1
    db.commit()


def actualizar(db: Session, empresa_id: int, datos: EmpresaUpdate) -> Empresa | None:
    return _aplicar_cambios(db, empresa_id, datos.model_dump())


def actualizar_parcial(
    db: Session, empresa_id: int, datos: EmpresaPatch
) -> Empresa | None:
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)
    return _aplicar_cambios(db, empresa_id, cambios)


def _preparar(campos: dict) -> dict:
    """Reemplaza la contraseña en texto plano por su hash antes de guardarla."""
    if "contrasena" in campos:
        campos["contrasena"] = hashear_contrasena(campos["contrasena"])
    return campos


def _aplicar_cambios(db: Session, empresa_id: int, cambios: dict) -> Empresa | None:
    empresa = db.get(Empresa, empresa_id)
    if empresa is None:
        return None
    nuevo_usuario = cambios.get("usuario")
    if nuevo_usuario is not None and nuevo_usuario != empresa.usuario:
        crud_intentos.renombrar(db, empresa.usuario, nuevo_usuario)
    for campo, valor in cambios.items():
        setattr(empresa, campo, valor)
    usuario = empresa.usuario
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise UsuarioYaExiste(usuario) from None
    db.refresh(empresa)
    return empresa


def eliminar(db: Session, empresa_id: int) -> bool:
    empresa = db.get(Empresa, empresa_id)
    if empresa is None:
        return False
    db.delete(empresa)
    db.commit()
    return True
