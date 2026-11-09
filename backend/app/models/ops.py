"""Analytics, scheduler and logging models."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, str_enum, utcnow
from app.models.enums import DataSource, JobStatus, LogLevel, SyncStatus, WorkerState


class AnalyticsDaily(Base):
    """Channel-level metrics per day, synced from YouTube Analytics API."""

    __tablename__ = "analytics_daily"
    __table_args__ = (UniqueConstraint("channel_id", "day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    views: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    watch_time_minutes: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    average_view_duration_sec: Mapped[float | None] = mapped_column(Float)
    average_view_percentage: Mapped[float | None] = mapped_column(Float)
    subscribers_gained: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    subscribers_lost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    likes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    data_source: Mapped[DataSource] = mapped_column(str_enum(DataSource, "data_source"), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AnalyticsVideo(Base):
    """Per-video metrics per day."""

    __tablename__ = "analytics_video"
    __table_args__ = (
        UniqueConstraint("video_id", "day"),
        Index("ix_analytics_video_channel_day", "channel_id", "day"),
        ForeignKeyConstraint(
            ["channel_id", "video_id"],
            ["videos.channel_id", "videos.id"],
            name="fk_analytics_video_video",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_id: Mapped[int] = mapped_column(Integer, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    views: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    watch_time_minutes: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    average_view_duration_sec: Mapped[float | None] = mapped_column(Float)
    average_view_percentage: Mapped[float | None] = mapped_column(Float)
    subscribers_gained: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    likes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    data_source: Mapped[DataSource] = mapped_column(str_enum(DataSource, "data_source"), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AnalyticsChannelSnapshot(Base):
    """Channel totals as reported by YouTube Data API (subscriber count is NOT in the daily report)."""

    __tablename__ = "analytics_channel_snapshots"
    __table_args__ = (UniqueConstraint("channel_id", "day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    # NULL when the owner hides the subscriber count (YouTube then returns no number)
    subscribers: Mapped[int | None] = mapped_column(BigInteger)
    subscribers_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    total_views: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    video_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    data_source: Mapped[DataSource] = mapped_column(str_enum(DataSource, "data_source"), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AnalyticsRetention(Base):
    """Audience retention curve of one video (audienceWatchRatio per elapsed-time ratio)."""

    __tablename__ = "analytics_video_retention"
    __table_args__ = (
        UniqueConstraint("video_id"),
        ForeignKeyConstraint(
            ["channel_id", "video_id"],
            ["videos.channel_id", "videos.id"],
            name="fk_analytics_retention_video",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # [[elapsed_ratio 0..1, audience_watch_ratio], ...] exactly as returned by YouTube
    points: Mapped[list] = mapped_column(default=list, nullable=False)
    data_source: Mapped[DataSource] = mapped_column(str_enum(DataSource, "data_source"), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AnalyticsSyncState(Base):
    """Per-channel sync bookkeeping: lets the UI tell 'real data' from 'not synced yet'."""

    __tablename__ = "analytics_sync_state"

    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[SyncStatus] = mapped_column(str_enum(SyncStatus, "sync_status"), nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # last day (inclusive) whose channel-level data was written; next sync restarts a few days earlier
    synced_through: Mapped[date | None] = mapped_column(Date)
    days_written: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    videos_synced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    videos_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # scope | auth | quota | network | api | internal
    error_kind: Mapped[str | None] = mapped_column(String(16))
    last_error: Mapped[str | None] = mapped_column(Text)
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SystemMetric(Base):
    """One monitoring sample per minute (CPU/RAM/disk/queues) for the Monitoring charts. Pruned by maintenance."""

    __tablename__ = "system_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    cpu_percent: Mapped[float] = mapped_column(Float, nullable=False)
    ram_percent: Mapped[float] = mapped_column(Float, nullable=False)
    ram_available_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    disk_free_gb: Mapped[float] = mapped_column(Float, nullable=False)
    ffmpeg_processes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ffmpeg_rss_mb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    render_queue: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    upload_queue: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SchedulerJob(TimestampMixin, Base):
    """Persistent job queue (survives restarts). `dedupe_key` prevents duplicates."""

    __tablename__ = "scheduler_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(default=dict, nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    status: Mapped[JobStatus] = mapped_column(
        str_enum(JobStatus, "job_status"), default=JobStatus.QUEUED, nullable=False, index=True
    )
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    timeout_sec: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    locked_by: Mapped[str | None] = mapped_column(String(100))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class SystemLog(Base):
    """Audit / activity log shown in 'Hoạt động gần đây' and Monitoring."""

    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=text("CURRENT_TIMESTAMP"),
        nullable=False, index=True,
    )
    level: Mapped[LogLevel] = mapped_column(str_enum(LogLevel, "log_level"), default=LogLevel.INFO, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"), index=True
    )
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[dict] = mapped_column(default=dict, nullable=False)


class WorkerStatus(Base):
    """Heartbeat of background worker processes (render worker; Phase 3+: upload/scheduler)."""

    __tablename__ = "worker_status"

    worker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), default="render", nullable=False)
    hostname: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[WorkerState] = mapped_column(
        str_enum(WorkerState, "worker_state"), default=WorkerState.IDLE, nullable=False
    )
    current_job_id: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    info: Mapped[dict] = mapped_column(default=dict, nullable=False)
