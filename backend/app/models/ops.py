"""Analytics, scheduler and logging models."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, str_enum, utcnow
from app.models.enums import DataSource, JobStatus, LogLevel


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
