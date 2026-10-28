"""quitar cantidad de trackings

Revision ID: 56f6fe5bed2e
Revises: ad8dcdac7372
Create Date: 2026-10-08 21:49:01.943657

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56f6fe5bed2e'
down_revision: Union[str, Sequence[str], None] = 'ad8dcdac7372'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """El seguimiento deja de registrar cantidad: solo lote y vencimiento.

    Las cantidades existentes se pierden.
    """
    op.drop_column('trackings', 'quantity')


def downgrade() -> None:
    """Vuelve a crear la columna. Las cantidades borradas no se recuperan:
    los seguimientos existentes quedan con cantidad 0."""
    op.add_column('trackings', sa.Column('quantity', sa.NUMERIC(precision=12, scale=3), server_default='0', nullable=False))
    op.alter_column('trackings', 'quantity', server_default=None)
