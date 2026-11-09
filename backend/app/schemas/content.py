from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import DURATION_CHOICES, ContentType, IdeaStatus, ProductionStatus
from app.render.audio import GENERATORS
from app.render.video import (
    BACKGROUND_MOTIONS,
    CHARACTER_MOTIONS,
    CHARACTER_POSITIONS,
    EFFECTS,
    OVERLAY_MODES,
    OVERLAY_POSITIONS,
)

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
X264_PRESETS = ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow")
RESOLUTIONS = {"1920x1080": (1920, 1080), "1280x720": (1280, 720), "2560x1440": (2560, 1440)}


class CharacterPlacement(BaseModel):
    position: str = "bottom_right"
    scale: float = Field(default=0.42, ge=0.15, le=0.9)
    motion: str = "bob"

    @field_validator("position")
    @classmethod
    def _pos(cls, v: str) -> str:
        if v not in CHARACTER_POSITIONS:
            raise ValueError(f"position phải là một trong {CHARACTER_POSITIONS}")
        return v

    @field_validator("motion")
    @classmethod
    def _motion(cls, v: str) -> str:
        if v not in CHARACTER_MOTIONS:
            raise ValueError(f"motion phải là một trong {tuple(CHARACTER_MOTIONS)}")
        return v


class AnimationConfig(BaseModel):
    background_motion: str = "slow_zoom"
    effects: list[str] = Field(default_factory=list, max_length=len(EFFECTS))
    character: CharacterPlacement = Field(default_factory=CharacterPlacement)

    @field_validator("background_motion")
    @classmethod
    def _bm(cls, v: str) -> str:
        if v not in BACKGROUND_MOTIONS:
            raise ValueError(f"background_motion phải là một trong {tuple(BACKGROUND_MOTIONS)}")
        return v

    @field_validator("effects")
    @classmethod
    def _fx(cls, v: list[str]) -> list[str]:
        bad = [e for e in v if e not in EFFECTS]
        if bad:
            raise ValueError(f"Hiệu ứng không hỗ trợ: {bad}. Cho phép: {tuple(EFFECTS)}")
        return sorted(set(v), key=list(EFFECTS).index)


class AudioLayerIn(BaseModel):
    kind: str = Field(description="asset | generator")
    asset_id: int | None = None
    generator: str | None = None
    volume: float = Field(default=0.8, ge=0.0, le=2.0)

    @model_validator(mode="after")
    def _check(self) -> "AudioLayerIn":
        if self.kind == "asset":
            if self.asset_id is None:
                raise ValueError("Lớp âm thanh 'asset' cần asset_id")
            self.generator = None
        elif self.kind == "generator":
            if self.generator not in GENERATORS:
                raise ValueError(f"generator phải là một trong {tuple(GENERATORS)}")
            self.asset_id = None
        else:
            raise ValueError("kind phải là 'asset' hoặc 'generator'")
        self.volume = round(self.volume, 2)
        return self


class PomodoroConfig(BaseModel):
    focus_min: int = Field(default=25, ge=5, le=120)
    short_break_min: int = Field(default=5, ge=0, le=60)
    long_break_min: int = Field(default=15, ge=0, le=60)
    cycles_before_long: int = Field(default=4, ge=0, le=12)


class OverlayConfig(BaseModel):
    mode: str = "none"
    position: str = "top_center"
    color: str = "#FFFFFF"
    box: bool = True
    font_asset_id: int | None = None
    labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in OVERLAY_MODES:
            raise ValueError(f"mode phải là một trong {tuple(OVERLAY_MODES)}")
        return v

    @field_validator("position")
    @classmethod
    def _pos(cls, v: str) -> str:
        if v not in OVERLAY_POSITIONS:
            raise ValueError(f"position phải là một trong {OVERLAY_POSITIONS}")
        return v

    @field_validator("color")
    @classmethod
    def _color(cls, v: str) -> str:
        if not HEX_RE.match(v):
            raise ValueError("color phải có dạng #RRGGBB")
        return v.upper()

    @field_validator("labels")
    @classmethod
    def _labels(cls, v: dict[str, str]) -> dict[str, str]:
        allowed = {"focus", "short_break", "long_break", "session"}
        return {k: s.strip()[:40] for k, s in v.items() if k in allowed and s.strip()}


class RenderSettings(BaseModel):
    overlay: OverlayConfig = Field(default_factory=OverlayConfig)
    chime: bool = False
    chime_volume: float = Field(default=0.6, ge=0.0, le=2.0)
    master_volume: float = Field(default=1.0, ge=0.1, le=2.0)
    resolution: str = "1920x1080"
    fps: int = 30
    crf: int | None = Field(default=None, ge=16, le=30)
    preset: str | None = None

    @field_validator("resolution")
    @classmethod
    def _res(cls, v: str) -> str:
        if v not in RESOLUTIONS:
            raise ValueError(f"resolution phải là một trong {tuple(RESOLUTIONS)}")
        return v

    @field_validator("fps")
    @classmethod
    def _fps(cls, v: int) -> int:
        if v not in (24, 25, 30):
            raise ValueError("fps phải là 24, 25 hoặc 30")
        return v

    @field_validator("preset")
    @classmethod
    def _preset(cls, v: str | None) -> str | None:
        if v is not None and v not in X264_PRESETS:
            raise ValueError(f"preset phải là một trong {X264_PRESETS}")
        return v


def _clean_tags(v: list[str]) -> list[str]:
    seen, out = set(), []
    for t in v:
        t = t.strip().replace("<", "").replace(">", "")
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t[:100])
    return out[:60]


class ContentFields(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    content_type: ContentType
    character_id: int | None = None
    theme: str = Field(default="", max_length=200)
    script: str = Field(default="", max_length=20000)
    setting: str = Field(default="", max_length=200)
    background_asset_id: int | None = None
    animation: AnimationConfig = Field(default_factory=AnimationConfig)
    audio_layers: list[AudioLayerIn] = Field(default_factory=list, max_length=8)
    duration_minutes: int = 60
    pomodoro: PomodoroConfig | None = None
    render_settings: RenderSettings = Field(default_factory=RenderSettings)
    youtube_title: str = Field(default="", max_length=100)
    youtube_description: str = Field(default="", max_length=5000)
    youtube_tags: list[str] = Field(default_factory=list, max_length=60)

    @field_validator("duration_minutes")
    @classmethod
    def _duration(cls, v: int) -> int:
        if v not in DURATION_CHOICES:
            raise ValueError(f"Thời lượng phải là một trong {DURATION_CHOICES} phút")
        return v

    @field_validator("youtube_tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return _clean_tags(v)

    @field_validator("youtube_title", "youtube_description")
    @classmethod
    def _no_angle(cls, v: str) -> str:
        return v.replace("<", "").replace(">", "")  # YouTube rejects < and >


class ContentCreate(ContentFields):
    template_id: int | None = None
    idea_id: int | None = None
    # When a template is given, unset fields are taken from it
    model_config = {"extra": "forbid"}


class ContentUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    title: str | None = Field(default=None, min_length=2, max_length=200)
    content_type: ContentType | None = None
    character_id: int | None = None
    clear_character: bool = False
    theme: str | None = Field(default=None, max_length=200)
    script: str | None = Field(default=None, max_length=20000)
    setting: str | None = Field(default=None, max_length=200)
    background_asset_id: int | None = None
    clear_background: bool = False
    animation: AnimationConfig | None = None
    audio_layers: list[AudioLayerIn] | None = Field(default=None, max_length=8)
    duration_minutes: int | None = None
    pomodoro: PomodoroConfig | None = None
    clear_pomodoro: bool = False
    render_settings: RenderSettings | None = None
    youtube_title: str | None = Field(default=None, max_length=100)
    youtube_description: str | None = Field(default=None, max_length=5000)
    youtube_tags: list[str] | None = Field(default=None, max_length=60)

    @field_validator("duration_minutes")
    @classmethod
    def _duration(cls, v: int | None) -> int | None:
        if v is not None and v not in DURATION_CHOICES:
            raise ValueError(f"Thời lượng phải là một trong {DURATION_CHOICES} phút")
        return v

    @field_validator("youtube_tags")
    @classmethod
    def _tags(cls, v: list[str] | None) -> list[str] | None:
        return _clean_tags(v) if v is not None else None

    @field_validator("youtube_title", "youtube_description")
    @classmethod
    def _no_angle(cls, v: str | None) -> str | None:
        return v.replace("<", "").replace(">", "") if v is not None else None


class JobBrief(BaseModel):
    id: int
    job_type: str
    status: str
    progress: float
    step: str
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    output_url: str | None = None


class ContentOut(BaseModel):
    id: int
    channel_id: int
    channel_name: str
    title: str
    content_type: ContentType
    character_id: int | None
    character_name: str | None
    character_version_id: int | None
    character_version_no: int | None
    character_current_version_id: int | None
    theme: str
    script: str
    setting: str
    background_asset_id: int | None
    background_url: str | None
    animation: dict
    audio_layers: list[dict]
    duration_minutes: int
    pomodoro: dict | None
    render_settings: dict
    youtube_title: str
    youtube_description: str
    youtube_tags: list[str]
    thumbnail_url: str | None
    status: ProductionStatus
    last_error: str | None
    template_id: int | None
    idea_id: int | None
    fingerprint: str | None
    video_count: int = 0
    latest_job: JobBrief | None = None
    created_at: datetime
    updated_at: datetime


class ValidationReport(BaseModel):
    ok: bool
    errors: list[str]
    warnings: list[str]


class MetadataOut(BaseModel):
    youtube_title: str
    youtube_description: str
    youtube_tags: list[str]
    applied: bool


class RenderRequest(BaseModel):
    job_type: str = Field(default="full", description="full | preview")
    preview_seconds: int = Field(default=60, ge=10, le=300)
    priority: int = Field(default=100, ge=1, le=1000)


class TemplateIn(BaseModel):
    channel_id: int | None = None
    name: str = Field(min_length=2, max_length=150)
    content_type: ContentType
    config: dict = Field(default_factory=dict)


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    config: dict | None = None


class TemplateOut(BaseModel):
    id: int
    channel_id: int | None
    name: str
    content_type: ContentType
    config: dict
    builtin: bool


class IdeaGenerate(BaseModel):
    count: int = Field(default=5, ge=1, le=20)
    content_type: ContentType | None = None


class IdeaOut(BaseModel):
    id: int
    channel_id: int
    title: str
    content_type: ContentType
    theme: str
    description: str
    attributes: dict
    status: IdeaStatus
    created_at: datetime
