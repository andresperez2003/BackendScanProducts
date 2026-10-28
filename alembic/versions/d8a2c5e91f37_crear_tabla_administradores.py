"""crear tabla administradores

Revision ID: d8a2c5e91f37
Revises: c3e8f1a7d924
Create Date: 2026-10-08 22:00:00.000000

El primer administrador se crea por consola: python -m app.cli crear-admin <usuario>
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8a2c5e91f37'
down_revision: Union[str, Sequence[str], None] = 'c3e8f1a7d924'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'administradores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('usuario', sa.String(length=50), nullable=False),
        sa.Column('contrasena', sa.String(length=255), nullable=False),
        sa.Column('version_token', sa.Integer(), server_default='0', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('usuario'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('administradores')
