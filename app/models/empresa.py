from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.plan import Plan


class Empresa(Base):
    __tablename__ = "empresas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    usuario: Mapped[str] = mapped_column(String(50), unique=True)
    contrasena: Mapped[str] = mapped_column(String(255))
    # Va dentro de cada token. Al cambiar la contraseña se incrementa y todos
    # los tokens emitidos antes dejan de ser válidos.
    version_token: Mapped[int] = mapped_column(default=0, server_default="0")
    # Plan de la lectura de fotos; None = sin plan (no puede leer fotos).
    # Solo cuentan las lecturas desde plan_desde; plan_hasta None = no vence (la demo).
    # RESTRICT: un plan que alguna empresa tiene no se puede borrar, solo desactivar.
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("planes.id", ondelete="RESTRICT"))
    plan_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plan: Mapped[Plan | None] = relationship()
