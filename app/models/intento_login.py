from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IntentoLogin(Base):
    """Intentos fallidos de login por nombre de usuario.

    Se guarda por usuario (no por empresa) para contar también los usuarios
    que no existen: así el bloqueo no revela qué usuarios son reales.
    """

    __tablename__ = "intentos_login"

    usuario: Mapped[str] = mapped_column(String(50), primary_key=True)
    fallidos: Mapped[int] = mapped_column(default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Para borrar las filas viejas y que la tabla no crezca sin límite.
    ultimo_fallo: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
