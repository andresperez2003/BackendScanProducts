from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.supplier import Supplier


class Product(Base):
    """Datos fijos del producto. El lote y la fecha de vencimiento
    están en sus seguimientos (Tracking): un producto puede tener varios lotes."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    unit: Mapped[str] = mapped_column(String(30))
    # Sin ondelete: la base impide borrar un proveedor que tenga productos
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True
    )
    # Lo pone la base al insertar; se usa para las estadísticas de registros por mes.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # "joined": se carga en la misma consulta, así un seguimiento trae su
    # producto y su proveedor sin consultas extra.
    supplier: Mapped[Supplier] = relationship(lazy="joined")
