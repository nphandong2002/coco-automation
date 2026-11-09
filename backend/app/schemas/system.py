from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LogOut(BaseModel):
    id: int
    created_at: datetime
    level: str
    category: str
    channel_id: int | None
    channel_name: str | None = None
    message: str
    details: dict


class MetricValue(BaseModel):
    """A metric with explicit provenance. value=None means not synced yet."""

    value: float | None
    source: str  # "youtube_api" | "estimated" | "not_synced"
    synced_at: datetime | None = None


class Overview(BaseModel):
    channels_total: int
    channels_by_status: dict[str, int]
    characters_total: int
    content_projects_total: int
    videos_produced: int
    render_jobs_running: int
    render_jobs_queued: int
    videos_waiting_publish: int
    total_views: MetricValue
    total_subscribers: MetricValue
    total_subscribers_gained: MetricValue
    total_watch_time_minutes: MetricValue
    daily_views: list[dict]  # [{day, views}] from YouTube API only; empty if not synced
    recent_activity: list[LogOut]


class SystemInfo(BaseModel):
    app_version: str
    database_ok: bool
    database_message: str
    migration_revision: str | None
    ffmpeg_path: str | None
    storage_dir: str
    disk_total_gb: float
    disk_free_gb: float
    cpu_percent: float
    ram_total_gb: float
    ram_used_percent: float
    secret_key_configured: bool
    dashboard_auth_enabled: bool
