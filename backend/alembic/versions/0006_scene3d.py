"""3D scenes: model assets (.glb) and content_projects.scene3d

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None

OLD = ('image', 'video', 'audio', 'font')
NEW = OLD + ('model',)


def _check(values):
    return "kind IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f('ck_assets_asset_kind'), 'assets', type_='check')
    op.create_check_constraint(op.f('ck_assets_asset_kind'), 'assets', _check(NEW))
    op.add_column('content_projects', sa.Column('scene3d', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('content_projects', 'scene3d')
    op.execute("DELETE FROM assets WHERE kind='model'")
    op.drop_constraint(op.f('ck_assets_asset_kind'), 'assets', type_='check')
    op.create_check_constraint(op.f('ck_assets_asset_kind'), 'assets', _check(OLD))
