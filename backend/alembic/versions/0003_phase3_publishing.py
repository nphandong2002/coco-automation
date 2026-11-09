"""phase3 publishing: upload worker state + one active publishing job per video

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

OLD = ('idle', 'rendering', 'waiting_lock', 'stopped')
NEW = ('idle', 'rendering', 'uploading', 'waiting_lock', 'stopped')


def _check(values):
    return "state IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f('ck_worker_status_worker_state'), 'worker_status', type_='check')
    op.create_check_constraint(op.f('ck_worker_status_worker_state'), 'worker_status', _check(NEW))
    op.create_index('uq_publishing_jobs_active_video', 'publishing_jobs', ['video_id'], unique=True,
                    postgresql_where=sa.text("status IN ('queued', 'running')"))


def downgrade() -> None:
    op.drop_index('uq_publishing_jobs_active_video', table_name='publishing_jobs')
    op.execute("UPDATE worker_status SET state='idle' WHERE state='uploading'")
    op.drop_constraint(op.f('ck_worker_status_worker_state'), 'worker_status', type_='check')
    op.create_check_constraint(op.f('ck_worker_status_worker_state'), 'worker_status', _check(OLD))
