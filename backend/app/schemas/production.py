from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class JobOut(BaseModel):
    id: int
    channel_id: int
    channel_name: str
    content_project_id: int
    project_title: str | None
    job_type: str
    status: str
    step: str
    progress: float
    attempts: int
    max_attempts: int
    priority: int
    worker_id: str | None
    heartbeat_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    duration_sec: float | None
    timeout_sec: int
    cancel_requested: bool
    error: str | None
    output_url: str | None
    video_id: int | None
    eta_seconds: float | None
    has_log: bool


class VideoOut(BaseModel):
    id: int
    channel_id: int
    channel_name: str
    content_project_id: int | None
    video_job_id: int | None
    title: str
    url: str
    thumbnail_url: str | None
    duration_sec: float
    width: int
    height: int
    fps: float
    size_bytes: int
    sha256: str | None
    qc_passed: bool
    qc_report: dict
    youtube_video_id: str | None
    privacy_status: str | None
    created_at: datetime


class WorkerOut(BaseModel):
    worker_id: str
    kind: str
    hostname: str
    pid: int
    state: str
    online: bool
    current_job_id: int | None
    started_at: datetime
    heartbeat_at: datetime
    info: dict


class ProductionStatusOut(BaseModel):
    workers: list[WorkerOut]
    queued: int
    running: int
    failed_24h: int
    succeeded_24h: int


class Capabilities(BaseModel):
    ffmpeg_path: str | None
    ffmpeg_version: str | None
    ffprobe_path: str | None
    drawtext: bool
    font_path: str | None
    render_threads: int
    render_preset: str
    render_crf: int
    loop_seconds: int
    durations: list[int]
    preview_seconds: list[int]
    generators: dict
    background_motions: dict
    effects: dict
    character_motions: dict
    character_positions: list[str]
    overlay_modes: dict
    overlay_positions: list[str]
    background_styles: dict
    resolutions: list[str]
    x264_presets: list[str]
