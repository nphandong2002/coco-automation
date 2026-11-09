"""phase4 analytics: channel snapshots, retention curves, sync state, 'syncing' worker state

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

OLD = ('idle', 'rendering', 'uploading', 'waiting_lock', 'stopped')
NEW = ('idle', 'rendering', 'uploading', 'syncing', 'waiting_lock', 'stopped')

DATA_SOURCE_CHECK = "data_source IN ('youtube_api', 'estimated')"


def _check(values):
    return "state IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f('ck_worker_status_worker_state'), 'worker_status', type_='check')
    op.create_check_constraint(op.f('ck_worker_status_worker_state'), 'worker_status', _check(NEW))

    op.create_table(
        'analytics_channel_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('subscribers', sa.BigInteger()),
        sa.Column('subscribers_hidden', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('total_views', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('video_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('data_source', sa.String(32), nullable=False),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_analytics_channel_snapshots')),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], name=op.f('fk_analytics_channel_snapshots_channel_id_channels'), ondelete='CASCADE'),
        sa.UniqueConstraint('channel_id', 'day', name=op.f('uq_analytics_channel_snapshots_channel_id_day')),
        sa.CheckConstraint(DATA_SOURCE_CHECK, name=op.f('ck_analytics_channel_snapshots_data_source')),
    )
    op.create_index('ix_analytics_channel_snapshots_channel_id', 'analytics_channel_snapshots', ['channel_id'])

    op.create_table(
        'analytics_video_retention',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('video_id', sa.Integer(), nullable=False),
        sa.Column('points', sa.JSON(), nullable=False),
        sa.Column('data_source', sa.String(32), nullable=False),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_analytics_video_retention')),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], name=op.f('fk_analytics_video_retention_channel_id_channels'), ondelete='CASCADE'),
        sa.UniqueConstraint('video_id', name=op.f('uq_analytics_video_retention_video_id')),
        sa.ForeignKeyConstraint(['channel_id', 'video_id'], ['videos.channel_id', 'videos.id'],
                                name='fk_analytics_retention_video', ondelete='CASCADE'),
        sa.CheckConstraint(DATA_SOURCE_CHECK, name=op.f('ck_analytics_video_retention_data_source')),
    )
    op.create_index('ix_analytics_video_retention_channel_id', 'analytics_video_retention', ['channel_id'])

    op.create_table(
        'analytics_sync_state',
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True)),
        sa.Column('last_success_at', sa.DateTime(timezone=True)),
        sa.Column('synced_through', sa.Date()),
        sa.Column('days_written', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('videos_synced', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('videos_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_kind', sa.String(16)),
        sa.Column('last_error', sa.Text()),
        sa.Column('retry_after', sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint('channel_id', name=op.f('pk_analytics_sync_state')),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], name=op.f('fk_analytics_sync_state_channel_id_channels'), ondelete='CASCADE'),
        sa.CheckConstraint("status IN ('ok', 'partial', 'error')", name=op.f('ck_analytics_sync_state_sync_status')),
    )

    # Analytics queries filter/aggregate by day; the unique (channel_id, day) index already covers
    # channel-level reads. Video-level reads by day range need their own index.
    op.create_index('ix_analytics_video_channel_day', 'analytics_video', ['channel_id', 'day'])


def downgrade() -> None:
    op.drop_index('ix_analytics_video_channel_day', table_name='analytics_video')
    op.drop_table('analytics_sync_state')
    op.drop_table('analytics_video_retention')
    op.drop_table('analytics_channel_snapshots')
    op.execute("UPDATE worker_status SET state='idle' WHERE state='syncing'")
    op.drop_constraint(op.f('ck_worker_status_worker_state'), 'worker_status', type_='check')
    op.create_check_constraint(op.f('ck_worker_status_worker_state'), 'worker_status', _check(OLD))
