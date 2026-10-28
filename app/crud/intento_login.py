from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.exceptions import CuentaBloqueada
from app.models.intento_login import IntentoLogin


def verificar_no_bloqueado(db: Session, usuario: str) -> None:
    """Lanza CuentaBloqueada si el usuario sigue dentro de su bloqueo."""
    intento = db.get(IntentoLogin, usuario)
    if intento is None or intento.bloqueado_hasta is None:
        return
    restante = intento.bloqueado_hasta - datetime.now(UTC)
    if restante > timedelta(0):
        raise CuentaBloqueada(restante)


def registrar_fallo(db: Session, usuario: str) -> None:
    """Suma un intento fallido. Al llegar al máximo bloquea y lanza CuentaBloqueada.

    Solo cuentan los fallos de los últimos N minutos: los más viejos se borran.
    """
    settings = get_settings()
    ahora = datetime.now(UTC)
    _borrar_viejos(db, ahora - timedelta(minutes=settings.minutos_bloqueo_login), ahora)
    # Upsert atómico: dos intentos al mismo tiempo no pueden perder la cuenta.
    fallidos = db.scalar(
        insert(IntentoLogin)
        .values(usuario=usuario, fallidos=1, ultimo_fallo=ahora)
        .on_conflict_do_update(
            index_elements=[IntentoLogin.usuario],
            set_={"fallidos": IntentoLogin.fallidos + 1, "ultimo_fallo": ahora},
        )
        .returning(IntentoLogin.fallidos)
    )
    if fallidos < settings.max_intentos_login:
        db.commit()
        return

    bloqueo = timedelta(minutes=settings.minutos_bloqueo_login)
    # El contador vuelve a 0: al terminar el bloqueo hay otros N intentos.
    db.execute(
        update(IntentoLogin)
        .where(IntentoLogin.usuario == usuario)
        .values(fallidos=0, bloqueado_hasta=ahora + bloqueo)
    )
    db.commit()
    raise CuentaBloqueada(bloqueo)


def _borrar_viejos(db: Session, limite: datetime, ahora: datetime) -> None:
    """Borra las filas sin fallos recientes que no estén bloqueadas.

    Sin esto, cada usuario inventado que alguien prueba deja una fila para siempre.
    """
    db.execute(
        delete(IntentoLogin).where(
            IntentoLogin.ultimo_fallo < limite,
            or_(IntentoLogin.bloqueado_hasta.is_(None), IntentoLogin.bloqueado_hasta < ahora),
        )
    )


def limpiar(db: Session, usuario: str) -> None:
    """Borra los intentos fallidos tras un login correcto."""
    db.execute(delete(IntentoLogin).where(IntentoLogin.usuario == usuario))
    db.commit()


def renombrar(db: Session, usuario_viejo: str, usuario_nuevo: str) -> None:
    """Mueve los intentos al nuevo nombre, para que cambiar de usuario no
    sirva para saltarse un bloqueo. No hace commit: va junto al cambio de usuario."""
    db.execute(delete(IntentoLogin).where(IntentoLogin.usuario == usuario_nuevo))
    db.execute(
        update(IntentoLogin)
        .where(IntentoLogin.usuario == usuario_viejo)
        .values(usuario=usuario_nuevo)
    )
