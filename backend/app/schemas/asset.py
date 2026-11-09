from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import AssetKind, AssetSource, LicenseType

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def clean_tags(v: list[str]) -> list[str]:
    seen, out = set(), []
    for t in v:
        t = t.strip().lower()
        if t and t not in seen and len(t) <= 40:
            seen.add(t)
            out.append(t)
    return out[:30]


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    tags: list[str] | None = Field(default=None, max_length=30)
    license_type: LicenseType | None = None
    license_source: str | None = Field(default=None, max_length=500)
    attribution: str | None = Field(default=None, max_length=500)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str] | None) -> list[str] | None:
        return clean_tags(v) if v is not None else None


class BackgroundGenerate(BaseModel):
    channel_id: int | None = Field(default=None, description="NULL = thư viện dùng chung")
    style: str = "bokeh"
    palette: list[str] | None = Field(default=None, max_length=6)
    seed: int | None = Field(default=None, ge=0, le=2_000_000_000)
    name: str = Field(default="", max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("palette")
    @classmethod
    def _palette(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for c in v:
            if not HEX_RE.match(c):
                raise ValueError(f"Màu '{c}' phải có dạng #RRGGBB")
        return [c.upper() for c in v]

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return clean_tags(v)


class AssetOut(BaseModel):
    id: int
    channel_id: int | None
    channel_name: str | None = None
    kind: AssetKind
    name: str
    url: str
    sha256: str
    size_bytes: int
    mime_type: str
    duration_sec: float | None
    width: int | None
    height: int | None
    license_type: LicenseType
    license_source: str
    attribution: str
    tags: list[str]
    source: AssetSource
    meta: dict
    created_at: datetime
