"""3D scene description stored in `content_projects.scene3d`.

One JSON document drives BOTH the live viewer in the dashboard (three.js) and — in the next step —
the headless frame capture used for rendering, so what you see is what gets rendered.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Vec3 = tuple[float, float, float]
PRESETS = ("cozy_room", "rainy_window", "forest_cabin", "cafe")
REACTION_TRIGGERS = ("click", "rain_heavy", "fire_out", "break_time")


def _bounded(v: Vec3, limit: float, name: str) -> Vec3:
    if any(abs(x) > limit for x in v):
        raise ValueError(f"{name} nằm ngoài phạm vi ±{limit}")
    return v


class Environment3D(BaseModel):
    time_of_day: Literal["day", "dusk", "night"] = "night"
    rain: float = Field(default=0.5, ge=0, le=1)
    wind: float = Field(default=0.2, ge=0, le=1)
    fog: float = Field(default=0.1, ge=0, le=1)
    fireplace: bool = True
    lamp: bool = True


class Character3D(BaseModel):
    asset_id: int | None = None                 # a .glb asset; None = built-in placeholder character
    position: Vec3 = (0.9, 0.0, -0.2)
    rotation_y: float = Field(default=-25, ge=-360, le=360)   # degrees
    scale: float = Field(default=1.0, ge=0.05, le=20)
    idle_animation: str | None = Field(default=None, max_length=80)
    # trigger -> animation clip name in the model, e.g. {"click": "Wave"}
    reactions: dict[str, str] = Field(default_factory=dict)

    @field_validator("position")
    @classmethod
    def _pos(cls, v: Vec3) -> Vec3:
        return _bounded(v, 20, "position")

    @field_validator("reactions")
    @classmethod
    def _reactions(cls, v: dict[str, str]) -> dict[str, str]:
        bad = [k for k in v if k not in REACTION_TRIGGERS]
        if bad:
            raise ValueError(f"Trigger không hợp lệ: {', '.join(bad)}. Cho phép: {', '.join(REACTION_TRIGGERS)}")
        return {k: n[:80] for k, n in v.items() if n}


class Camera3D(BaseModel):
    position: Vec3 = (0.0, 1.5, 3.6)
    target: Vec3 = (0.0, 0.9, 0.0)
    fov: float = Field(default=45, ge=20, le=90)

    @field_validator("position", "target")
    @classmethod
    def _vec(cls, v: Vec3) -> Vec3:
        return _bounded(v, 50, "camera")


class Scene3D(BaseModel):
    version: Literal[1] = 1
    preset: Literal["cozy_room", "rainy_window", "forest_cabin", "cafe"] = "cozy_room"
    environment: Environment3D = Field(default_factory=Environment3D)
    character: Character3D = Field(default_factory=Character3D)
    camera: Camera3D = Field(default_factory=Camera3D)
