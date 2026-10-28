from datetime import date, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.product import Product
from app.models.supplier import Supplier


class Tracking(Base):
    """Seguimiento de un lote de un producto y su fecha de vencimiento.

    El proveedor no se guarda aquí: se obtiene a través del producto.
    """

    __tablename__ = "trackings"
    # Un mismo producto no puede repetir número de lote.
    __table_args__ = (UniqueConstraint("product_id", "batch", name="uq_trackings_product_batch"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    batch: Mapped[str] = mapped_column(String(50))
    due_date: Mapped[date | None]
    # Sin ondelete: la base impide borrar un producto que tenga seguimientos
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product: Mapped[Product] = relationship(lazy="joined")

    @property
    def supplier(self) -> Supplier:
        return self.product.supplier
