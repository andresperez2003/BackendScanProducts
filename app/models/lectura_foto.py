from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LecturaFoto(Base):
    """Una lectura de foto exitosa: cuenta para el límite del plan de la empresa.

    No guarda la foto ni el resultado, solo cuándo se hizo.
    """

    __tablename__ = "lecturas_foto"
    __table_args__ = (Index("ix_lecturas_foto_empresa_creada", "empresa_id", "creada_en"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"))
    # Hora de Python, igual que Empresa.plan_desde, para compararlas sin
    # depender de que el reloj de la base coincida.
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
