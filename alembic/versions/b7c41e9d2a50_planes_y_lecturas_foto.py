"""planes y lecturas_foto

Revision ID: b7c41e9d2a50
Revises: 56f6fe5bed2e
Create Date: 2026-10-08 12:00:00.000000

Las empresas que ya existen quedan en el plan demo, con el contador en cero.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c41e9d2a50'
down_revision: Union[str, Sequence[str], None] = '56f6fe5bed2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('empresas', sa.Column('plan', sa.String(length=20), server_default='demo', nullable=False))
    op.add_column('empresas', sa.Column('plan_desde', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('empresas', sa.Column('plan_hasta', sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        'lecturas_foto',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('creada_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lecturas_foto_empresa_creada', 'lecturas_foto', ['empresa_id', 'creada_en'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_lecturas_foto_empresa_creada', table_name='lecturas_foto')
    op.drop_table('lecturas_foto')
    op.drop_column('empresas', 'plan_hasta')
    op.drop_column('empresas', 'plan_desde')
    op.drop_column('empresas', 'plan')
