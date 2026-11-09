"""Overview dashboard + system info. Every number comes from the database or the OS.

Analytics totals only include rows whose data_source is 'youtube_api'. When no
row has been synced yet the metric is returned with source='not_synced' and
value=None, so the UI can show "chưa đồng bộ" instead of a fake 0.
"""
from __future__ import annotations

import shutil
from datetime import date, timedelta

import psutil
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import check_database
from app.core.storage import storage_root
from app.models import (
    AnalyticsChannelSnapshot,
    AnalyticsDaily,
    Channel,
    Character,
    ContentProject,
    PublishingJob,
    SystemLog,
    Video,
    VideoJob,
)
from app.models.enums import DataSource, JobStatus
from app.schemas.system import LogOut, MetricValue, Overview, SystemInfo
from app.services.channel_service import list_channels


def recent_logs(db: Session, limit: int = 20, channel_id: int | None = None,
                category: str | None = None) -> list[LogOut]:
    stmt = (
        select(SystemLog, Channel.name)
        .outerjoin(Channel, Channel.id == SystemLog.channel_id)
        .order_by(SystemLog.created_at.desc(), SystemLog.id.desc())
        .limit(min(max(limit, 1), 500))
    )
    if channel_id is not None:
        stmt = stmt.where(SystemLog.channel_id == channel_id)
    if category:
        stmt = stmt.where(SystemLog.category == category)
    return [
        LogOut(id=l.id, created_at=l.created_at, level=l.level.value, category=l.category,
               channel_id=l.channel_id, channel_name=name, message=l.message, details=l.details)
        for l, name in db.execute(stmt).all()
    ]


def _metric(db: Session, column) -> MetricValue:  # noqa: ANN001
    row = db.execute(
        select(func.sum(column), func.count(), func.max(AnalyticsDaily.synced_at))
        .where(AnalyticsDaily.data_source == DataSource.YOUTUBE_API)
    ).one()
    total, n, synced = row
    if not n:
        return MetricValue(value=None, source="not_synced")
    return MetricValue(value=float(total or 0), source=DataSource.YOUTUBE_API.value, synced_at=synced)


def _subscribers_metric(db: Session) -> MetricValue:
    """Sum of each channel's latest Data-API subscriber count (hidden counts are excluded)."""
    t = AnalyticsChannelSnapshot
    latest = select(t.channel_id.label("cid"), func.max(t.day).label("d")).group_by(t.channel_id).subquery()
    rows = db.execute(
        select(t.subscribers, t.synced_at)
        .join(latest, (latest.c.cid == t.channel_id) & (latest.c.d == t.day))
        .where(t.subscribers.is_not(None))
    ).all()
    if not rows:
        return MetricValue(value=None, source="not_synced")
    return MetricValue(value=float(sum(r[0] for r in rows)), source=DataSource.YOUTUBE_API.value,
                       synced_at=max(r[1] for r in rows))


def overview(db: Session) -> Overview:
    channels = list_channels(db)
    by_status: dict[str, int] = {"active": 0, "paused": 0, "error": 0, "disconnected": 0}
    for c in channels:
        by_status[c.status.value] += 1

    def count(stmt) -> int:  # noqa: ANN001
        return int(db.scalar(stmt) or 0)

    since = date.today() - timedelta(days=30)
    daily = db.execute(
        select(AnalyticsDaily.day, func.sum(AnalyticsDaily.views))
        .where(AnalyticsDaily.data_source == DataSource.YOUTUBE_API, AnalyticsDaily.day >= since)
        .group_by(AnalyticsDaily.day)
        .order_by(AnalyticsDaily.day)
    ).all()

    return Overview(
        channels_total=len(channels),
        channels_by_status=by_status,
        characters_total=count(select(func.count()).select_from(Character)),
        content_projects_total=count(select(func.count()).select_from(ContentProject)),
        videos_produced=count(select(func.count()).select_from(Video)),
        render_jobs_running=count(
            select(func.count()).select_from(VideoJob).where(VideoJob.status == JobStatus.RUNNING)),
        render_jobs_queued=count(
            select(func.count()).select_from(VideoJob).where(VideoJob.status == JobStatus.QUEUED)),
        videos_waiting_publish=count(
            select(func.count()).select_from(PublishingJob)
            .where(PublishingJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))),
        total_views=_metric(db, AnalyticsDaily.views),
        total_subscribers=_subscribers_metric(db),
        total_subscribers_gained=_metric(db, AnalyticsDaily.subscribers_gained),
        total_watch_time_minutes=_metric(db, AnalyticsDaily.watch_time_minutes),
        daily_views=[{"day": d.isoformat(), "views": int(v)} for d, v in daily],
        recent_activity=recent_logs(db, 15),
    )


def _ffmpeg_path() -> str | None:
    """The ffmpeg the renderer will really use (FFMPEG_PATH, PATH, or the bundled binary on Windows)."""
    try:
        from app.render.ffmpeg import ffmpeg_bin
        return str(ffmpeg_bin())
    except Exception:  # noqa: BLE001 - FFmpegNotFound
        return None


def system_info(db: Session) -> SystemInfo:
    settings = get_settings()
    ok, msg = check_database()
    revision = None
    if ok:
        try:
            revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:  # table missing when DB not migrated
            db.rollback()
    root = storage_root()
    disk = shutil.disk_usage(root)
    mem = psutil.virtual_memory()
    return SystemInfo(
        app_version=settings.app_version,
        database_ok=ok,
        database_message=msg,
        migration_revision=revision,
        ffmpeg_path=_ffmpeg_path(),
        storage_dir=str(root),
        disk_total_gb=round(disk.total / 1024**3, 1),
        disk_free_gb=round(disk.free / 1024**3, 1),
        cpu_percent=psutil.cpu_percent(interval=0.2),
        ram_total_gb=round(mem.total / 1024**3, 1),
        ram_used_percent=mem.percent,
        secret_key_configured=bool(settings.secret_key),
        dashboard_auth_enabled=bool(settings.dashboard_password),
    )
