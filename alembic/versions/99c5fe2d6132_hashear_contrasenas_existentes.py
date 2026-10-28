"""hashear contrasenas existentes

Revision ID: 99c5fe2d6132
Revises: e310ed46e9a6
Create Date: 2026-10-02 03:12:30.412577

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pwdlib import PasswordHash


# revision identifiers, used by Alembic.
revision: str = '99c5fe2d6132'
down_revision: Union[str, Sequence[str], None] = 'e310ed46e9a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Hashea las contraseñas guardadas en texto plano antes del login."""
    # Se usa pwdlib directamente (no app.security) para que la migración
    # no cambie si el código de la app cambia en el futuro.
    password_hash = PasswordHash.recommended()
    conn = op.get_bind()
    filas = conn.execute(
        sa.text("SELECT id, contrasena FROM empresas WHERE contrasena NOT LIKE '$argon2%'")
    ).all()
    for empresa_id, contrasena in filas:
        conn.execute(
            sa.text("UPDATE empresas SET contrasena = :hash WHERE id = :id"),
            {"hash": password_hash.hash(contrasena), "id": empresa_id},
        )


def downgrade() -> None:
    """Un hash no se puede revertir a texto plano: no hace nada."""
    pass
