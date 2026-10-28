from sqlalchemy import CheckConstraint, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Plan(Base):
    """Plan de la lectura automática de fotos (lote y vencimiento).

    Se editan desde el panel de administrador. El plan demo (`es_demo`) es el
    que recibe cada empresa al registrarse: sus lecturas son en total y no
    vence (`dias` None). Los pagos duran `dias` desde que se activan.
    """

    __tablename__ = "planes"
    __table_args__ = (
        CheckConstraint("precio >= 0", name="ck_planes_precio"),
        CheckConstraint("lecturas >= 0", name="ck_planes_lecturas"),
        CheckConstraint("dias IS NULL OR dias > 0", name="ck_planes_dias"),
        # Solo puede haber un plan demo.
        Index("uq_planes_demo", "es_demo", unique=True, postgresql_where=text("es_demo")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True)
    precio: Mapped[int]  # pesos por periodo; 0 en la demo
    lecturas: Mapped[int]  # por periodo; en la demo, en total
    dias: Mapped[int | None]  # duración del periodo; None = no vence
    es_demo: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Inactivo: no se puede asignar a más empresas; las que lo tienen lo conservan.
    activo: Mapped[bool] = mapped_column(default=True, server_default="true")
