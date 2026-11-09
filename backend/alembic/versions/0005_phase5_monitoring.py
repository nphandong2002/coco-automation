"""phase5 monitoring: system_metrics samples

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'system_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cpu_percent', sa.Float(), nullable=False),
        sa.Column('ram_percent', sa.Float(), nullable=False),
        sa.Column('ram_available_mb', sa.Integer(), nullable=False),
        sa.Column('disk_free_gb', sa.Float(), nullable=False),
        sa.Column('ffmpeg_processes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ffmpeg_rss_mb', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('render_queue', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('upload_queue', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_system_metrics')),
    )
    op.create_index(op.f('ix_system_metrics_ts'), 'system_metrics', ['ts'])


def downgrade() -> None:
    op.drop_index(op.f('ix_system_metrics_ts'), table_name='system_metrics')
    op.drop_table('system_metrics')
