from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ChannelStatus

CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ScheduleSlot(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0=Thứ Hai ... 6=Chủ Nhật")
    time: str = Field(description="HH:MM")

    @field_validator("time")
    @classmethod
    def _time(cls, v: str) -> str:
        if not TIME_RE.match(v):
            raise ValueError("Giờ phải có dạng HH:MM")
        return v


class PublishSchedule(BaseModel):
    timezone: str = "Asia/Bangkok"
    slots: list[ScheduleSlot] = Field(default_factory=list, max_length=50)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Múi giờ không hợp lệ: {v}") from exc
        return v


class VisualStyle(BaseModel):
    theme: str = ""
    mood: str = ""
    palette: list[str] = Field(default_factory=list, max_length=12)
    keywords: list[str] = Field(default_factory=list, max_length=30)


class AudioStyle(BaseModel):
    ambience: list[str] = Field(default_factory=list, max_length=30)
    music: str = ""
    notes: str = ""


def _clean_list(values: list[str]) -> list[str]:
    seen, out = set(), []
    for v in values:
        v = v.strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


class ChannelFields(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str = Field(default="", max_length=5000)
    language: str = Field(default="en", min_length=2, max_length=16)
    target_country: str = Field(default="US", min_length=2, max_length=8)
    topics: list[str] = Field(default_factory=list, max_length=30)
    visual_style: VisualStyle = Field(default_factory=VisualStyle)
    audio_style: AudioStyle = Field(default_factory=AudioStyle)
    publish_schedule: PublishSchedule = Field(default_factory=PublishSchedule)

    @field_validator("topics")
    @classmethod
    def _topics(cls, v: list[str]) -> list[str]:
        return _clean_list(v)


def validate_code(v: str) -> str:
    v = v.strip().lower()
    if not CODE_RE.match(v):
        raise ValueError("Mã kênh chỉ gồm a-z, 0-9, '-' (3–64 ký tự)")
    return v


class ChannelCreate(ChannelFields):
    code: str = Field(description="Mã định danh, chữ thường, số và '-', VD: cozy-study")

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        return validate_code(v)


class ChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=5000)
    language: str | None = Field(default=None, min_length=2, max_length=16)
    target_country: str | None = Field(default=None, min_length=2, max_length=8)
    topics: list[str] | None = Field(default=None, max_length=30)
    visual_style: VisualStyle | None = None
    audio_style: AudioStyle | None = None
    publish_schedule: PublishSchedule | None = None

    @field_validator("topics")
    @classmethod
    def _topics(cls, v: list[str] | None) -> list[str] | None:
        return _clean_list(v) if v is not None else None


class ChannelClone(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    code: str
    include_characters: bool = True

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        return validate_code(v)


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str
    language: str
    target_country: str
    topics: list[str]
    visual_style: dict
    audio_style: dict
    publish_schedule: dict
    status: ChannelStatus
    enabled: bool
    last_error: str | None
    last_error_at: datetime | None
    youtube_connected: bool
    youtube_channel_title: str | None = None
    avatar_url: str | None = None
    banner_url: str | None = None
    cloned_from_id: int | None
    character_count: int = 0
    created_at: datetime
    updated_at: datetime


class ChannelSummary(BaseModel):
    """Per-channel counters for the Channel Detail page (all from DB)."""

    characters_owned: int
    characters_granted: int
    content_projects: int
    videos: int
    render_jobs_active: int
    publishing_jobs_pending: int
    analytics_days_synced: int
