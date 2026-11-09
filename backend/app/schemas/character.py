from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import CharacterRole

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _clean(values: list[str]) -> list[str]:
    seen, out = set(), []
    for v in values:
        v = v.strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


class VersionFields(BaseModel):
    """Visual identity fields. All optional so a new version only overrides what changed."""

    appearance: str | None = Field(default=None, max_length=5000)
    art_style: str | None = Field(default=None, max_length=200)
    primary_colors: list[str] | None = Field(default=None, max_length=12)
    outfit: str | None = Field(default=None, max_length=2000)
    personality: str | None = Field(default=None, max_length=2000)
    usual_settings: list[str] | None = Field(default=None, max_length=30)
    allowed_animations: list[str] | None = Field(default=None, max_length=30)

    @field_validator("primary_colors")
    @classmethod
    def _colors(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for c in v:
            if not HEX_RE.match(c):
                raise ValueError(f"Màu '{c}' phải có dạng #RRGGBB")
        return [c.upper() for c in _clean(v)]

    @field_validator("usual_settings", "allowed_animations")
    @classmethod
    def _lists(cls, v: list[str] | None) -> list[str] | None:
        return _clean(v) if v is not None else None


class CharacterCreate(VersionFields):
    name: str = Field(min_length=1, max_length=120)
    species: str = Field(default="", max_length=80)
    role: CharacterRole = CharacterRole.SECONDARY


class CharacterUpdate(BaseModel):
    """Non-visual attributes (do not create a new version)."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    species: str | None = Field(default=None, max_length=80)
    archived: bool | None = None


class VersionCreate(VersionFields):
    change_note: str = Field(default="", max_length=500)


class RoleUpdate(BaseModel):
    role: CharacterRole


class GrantCreate(BaseModel):
    target_channel_id: int
    role: CharacterRole = CharacterRole.SECONDARY
    note: str = Field(default="", max_length=300)


class Expression(BaseModel):
    name: str
    image: str
    image_url: str


class VersionOut(BaseModel):
    id: int
    version_no: int
    appearance: str
    art_style: str
    primary_colors: list[str]
    outfit: str
    personality: str
    usual_settings: list[str]
    allowed_animations: list[str]
    expressions: list[Expression]
    avatar_url: str | None
    full_body_url: str | None
    reference_images: list[dict]
    change_note: str
    created_at: datetime
    is_current: bool


class ShareInfo(BaseModel):
    channel_id: int
    channel_name: str
    role: CharacterRole
    granted_at: datetime


class CharacterOut(BaseModel):
    id: int
    name: str
    species: str
    archived: bool
    owner_channel_id: int
    owner_channel_name: str
    # role/ownership relative to the channel in the URL
    channel_id: int
    role: CharacterRole
    is_owner: bool
    version_count: int
    current_version: VersionOut | None
    shared_with: list[ShareInfo]
    created_at: datetime
    updated_at: datetime
