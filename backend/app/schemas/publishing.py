from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import PrivacyStatus


class PublishCreate(BaseModel):
    video_id: int
    title: str | None = Field(default=None, max_length=100)        # default: content project's YouTube title
    description: str | None = Field(default=None, max_length=5000)
    tags: list[str] | None = None
    # Default PRIVATE so the video can be reviewed on YouTube before going public
    privacy: PrivacyStatus = PrivacyStatus.PRIVATE
    publish_at: datetime | None = None          # scheduled public time (timezone-aware)
    use_next_slot: bool = False                 # take the next free slot of the channel's schedule
    playlist_id: str | None = Field(default=None, max_length=64)
    category_id: str = Field(default="10", max_length=8)   # 10 = Music, 22 = People & Blogs, 27 = Education
    upload_after: datetime | None = None        # delay starting the upload (e.g. off-peak hours)


class PublishJobOut(BaseModel):
    id: int
    channel_id: int
    channel_name: str
    video_id: int
    video_title: str | None
    thumbnail_url: str | None
    status: str
    privacy_status: str
    publish_at: datetime | None
    title: str
    description: str
    tags: list[str]
    playlist_id: str | None
    category_id: str
    bytes_uploaded: int
    size_bytes: int | None
    progress: float | None
    attempts: int
    max_attempts: int
    next_attempt_at: datetime | None
    youtube_video_id: str | None
    youtube_url: str | None
    uploaded_at: datetime | None
    last_error: str | None
    history: list[dict]
    created_at: datetime


class YoutubeStatusOut(BaseModel):
    configured: bool
    connected: bool
    status: str
    youtube_channel_id: str | None
    youtube_channel_title: str | None
    google_account_email: str | None
    scopes: list[str]
    token_expiry: datetime | None
    last_refresh_at: datetime | None
    last_error: str | None


class YoutubeConfigOut(BaseModel):
    configured: bool
    redirect_uri: str
    scopes: list[str]


class AuthUrlOut(BaseModel):
    auth_url: str


class PlaylistOut(BaseModel):
    id: str
    title: str
    privacy: str | None


class SlotsOut(BaseModel):
    timezone: str
    slots: list[datetime]


class PublishStatusOut(BaseModel):
    counts: dict[str, int]
    workers: list[dict]
