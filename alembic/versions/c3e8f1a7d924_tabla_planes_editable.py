"""tabla planes editable

Revision ID: c3e8f1a7d924
Revises: b7c41e9d2a50
Create Date: 2026-10-08 21:00:00.000000

Los planes pasan del código a la tabla `planes` (se editan desde el panel de
administrador) y `empresas.plan` (texto) se reemplaza por `plan_id`.
Las empresas que estaban en la demo quedan sin plan; las de Básico o Pro
conservan su plan y su periodo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e8f1a7d924'
down_revision: Union[str, Sequence[str], None] = 'b7c41e9d2a50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (código anterior, nombre, precio, lecturas, días, es_demo)
PLANES = [
    ('demo', 'Demo', 0, 10, None, True),
    ('basico', 'Básico', 15000, 500, 30, False),
    ('pro', 'Pro', 28000, 1000, 30, False),
]


def upgrade() -> None:
    """Upgrade schema."""
    planes = op.create_table(
        'planes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=50), nullable=False),
        sa.Column('precio', sa.Integer(), nullable=False),
        sa.Column('lecturas', sa.Integer(), nullable=False),
        sa.Column('dias', sa.Integer(), nullable=True),
        sa.Column('es_demo', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('activo', sa.Boolean(), server_default='true', nullable=False),
        sa.CheckConstraint('precio >= 0', name='ck_planes_precio'),
        sa.CheckConstraint('lecturas >= 0', name='ck_planes_lecturas'),
        sa.CheckConstraint('dias IS NULL OR dias > 0', name='ck_planes_dias'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nombre'),
    )
    op.create_index('uq_planes_demo', 'planes', ['es_demo'], unique=True, postgresql_where=sa.text('es_demo'))
    op.bulk_insert(
        planes,
        [
            {'nombre': nombre, 'precio': precio, 'lecturas': lecturas, 'dias': dias, 'es_demo': es_demo}
            for _, nombre, precio, lecturas, dias, es_demo in PLANES
        ],
    )

    op.add_column('empresas', sa.Column('plan_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_empresas_plan_id', 'empresas', 'planes', ['plan_id'], ['id'], ondelete='RESTRICT')
    for codigo, nombre, *_ in PLANES:
        if codigo != 'demo':
            op.execute(
                sa.text(
                    "UPDATE empresas SET plan_id = (SELECT id FROM planes WHERE nombre = :nombre) "
                    "WHERE plan = :codigo"
                ).bindparams(nombre=nombre, codigo=codigo)
            )
    op.alter_column('empresas', 'plan_desde', nullable=True, server_default=None)
    op.execute("UPDATE empresas SET plan_desde = NULL, plan_hasta = NULL WHERE plan_id IS NULL")
    op.drop_column('empresas', 'plan')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('empresas', sa.Column('plan', sa.String(length=20), server_default='demo', nullable=False))
    for codigo, nombre, *_ in PLANES:
        op.execute(
            sa.text(
                "UPDATE empresas SET plan = :codigo "
                "WHERE plan_id = (SELECT id FROM planes WHERE nombre = :nombre)"
            ).bindparams(nombre=nombre, codigo=codigo)
        )
    op.execute("UPDATE empresas SET plan_desde = now() WHERE plan_desde IS NULL")
    op.alter_column('empresas', 'plan_desde', nullable=False, server_default=sa.text('now()'))
    op.drop_constraint('fk_empresas_plan_id', 'empresas', type_='foreignkey')
    op.drop_column('empresas', 'plan_id')
    op.drop_index('uq_planes_demo', table_name='planes', postgresql_where=sa.text('es_demo'))
    op.drop_table('planes')
