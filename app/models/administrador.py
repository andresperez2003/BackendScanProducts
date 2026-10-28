from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Administrador(Base):
    """Superadministrador de la plataforma: asigna planes y ve el consumo.

    Está separado de las empresas: no tiene productos ni seguimientos, y su
    token (tipo "admin") solo sirve en /admin. Se crea por consola:
    python -m app.cli crear-admin <usuario>
    """

    __tablename__ = "administradores"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    usuario: Mapped[str] = mapped_column(String(50), unique=True)
    contrasena: Mapped[str] = mapped_column(String(255))
    # Como en Empresa: al cambiar la contraseña se incrementa e invalida los tokens anteriores.
    version_token: Mapped[int] = mapped_column(default=0, server_default="0")
