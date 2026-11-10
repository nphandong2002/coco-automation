"""Application configuration loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Coco Automation"
    app_version: str = "0.5.0"
    environment: str = "production"

    host: str = "0.0.0.0"
    port: int = 8080

    database_url: str = "postgresql+psycopg://coco:coco@localhost:5432/coco"
    # Windows/portable mode: Coco runs its own private PostgreSQL (bundled by the `pgserver` package)
    # on 127.0.0.1 using the port/user/password from DATABASE_URL. See docs/WINDOWS.md.
    embedded_pg: bool = False
    pg_data_dir: Path = PROJECT_ROOT / "data" / "pgdata"

    # Root folder for all generated/uploaded files (videos, images, audio ...)
    storage_dir: Path = PROJECT_ROOT / "storage"
    # Built frontend (vite build output)
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"

    # Fernet key used to encrypt OAuth tokens at rest. REQUIRED.
    secret_key: str = Field(default="", description="Fernet key (urlsafe base64, 32 bytes)")

    # Optional HTTP Basic auth for the dashboard (recommended on shared LAN)
    dashboard_username: str = "admin"
    dashboard_password: str = ""

    max_upload_mb: int = 25
    log_level: str = "INFO"
    log_dir: Path = PROJECT_ROOT / "logs"

    # ---------------------------------------------------------------- Phase 2: assets
    # Audio/video assets can be large: they are streamed to disk, never held in RAM.
    max_asset_upload_mb: int = 2048
    max_model_upload_mb: int = 200   # .glb 3D models

    # ---------------------------------------------------------------- Phase 2: rendering
    ffmpeg_path: str = ""          # empty = find "ffmpeg" on PATH
    ffprobe_path: str = ""         # empty = find "ffprobe" on PATH (optional, ffmpeg fallback)
    font_path: str = ""            # TTF/OTF for timer + thumbnail text; empty = auto-detect
    render_threads: int = 0        # 0 = CPU cores - 1 (min 1)
    render_preset: str = "veryfast"
    render_crf: int = 22
    render_max_bitrate_kbps: int = 4500
    render_audio_bitrate_kbps: int = 192
    render_nice: int = 10          # lower CPU priority so the dashboard stays responsive
    render_loop_seconds: int = 60  # length of the seamless visual loop
    render_timeout_factor: float = 3.0   # job timeout = max(1h, duration * factor)
    min_free_disk_gb: float = 5.0

    # ---------------------------------------------------------------- Phase 2: worker
    worker_poll_seconds: float = 3.0
    worker_heartbeat_seconds: float = 10.0
    worker_stale_seconds: int = 180


    # ---------------------------------------------------------------- Phase 3: YouTube
    # OAuth client of YOUR Google Cloud project (Desktop/Web). Each channel still authorises
    # separately and gets its own encrypted refresh token.
    google_client_id: str = ""
    google_client_secret: str = ""
    # Must be registered in Google Cloud as an authorised redirect URI.
    oauth_redirect_uri: str = "http://localhost:8080/api/youtube/oauth/callback"
    youtube_upload_chunk_mb: int = 8       # resumable upload chunk (multiple of 256 KiB)
    youtube_http_timeout_sec: float = 60.0
    publish_retry_base_sec: int = 120      # exponential backoff base
    publish_retry_max_sec: int = 6 * 3600
    publish_poll_seconds: float = 5.0

    # ---------------------------------------------------------------- Phase 4: analytics
    analytics_sync_interval_minutes: int = 360   # auto-sync each connected channel this often
    analytics_initial_days: int = 90             # first sync looks back this many days
    analytics_overlap_days: int = 7              # re-read recent days: YouTube revises them
    analytics_max_backfill_days: int = 730
    analytics_max_videos_per_sync: int = 60      # per channel, oldest-synced first
    analytics_max_retention_per_sync: int = 15   # retention curves fetched per channel per sync
    analytics_retention_min_age_days: int = 3
    analytics_retention_refresh_hours: int = 24
    analytics_preliminary_days: int = 3          # newest days are flagged "preliminary"
    analytics_poll_seconds: float = 15.0

    # ---------------------------------------------------------------- Phase 5: monitoring & recovery
    monitor_interval_seconds: int = 60           # sampling + watchdog period
    metrics_retention_days: int = 7
    log_retention_days: int = 90                 # system_logs rows older than this are pruned
    min_free_ram_mb: int = 700                   # render worker waits instead of starting a job below this
    ram_warn_percent: float = 90.0
    disk_warn_gb: float = 15.0                   # warning; below min_free_disk_gb it is critical
    publish_stall_seconds: int = 600             # RUNNING upload with no progress this long = hung
    watchdog_kill_grace_seconds: int = 20        # SIGTERM first, SIGKILL after this
    tmp_max_age_hours: int = 24                  # leftover render temp files older than this are removed


@lru_cache
def get_settings() -> Settings:
    return Settings()
