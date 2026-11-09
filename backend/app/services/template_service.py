"""Video templates: reusable render configurations (shared or per channel)."""
from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Channel, ContentProject, VideoTemplate
from app.models.enums import DURATION_CHOICES
from app.schemas.content import AnimationConfig, AudioLayerIn, PomodoroConfig, RenderSettings, TemplateIn, TemplateOut, TemplateUpdate
from app.services import activity
from app.services.errors import AppError, NotFound


def template_out(t: VideoTemplate) -> TemplateOut:
    return TemplateOut(id=t.id, channel_id=t.channel_id, name=t.name, content_type=t.content_type,
                       config=t.config, builtin=bool((t.config or {}).get("builtin")))


def list_templates(db: Session, channel_id: int | None = None) -> list[TemplateOut]:
    stmt = select(VideoTemplate)
    if channel_id is not None:
        stmt = stmt.where(or_(VideoTemplate.channel_id.is_(None), VideoTemplate.channel_id == channel_id))
    return [template_out(t) for t in db.scalars(stmt.order_by(VideoTemplate.channel_id.nulls_first(),
                                                               VideoTemplate.id)).all()]


def get_template(db: Session, template_id: int) -> VideoTemplate:
    t = db.get(VideoTemplate, template_id)
    if t is None:
        raise NotFound(f"Không tìm thấy template #{template_id}")
    return t


def validate_config(cfg: dict) -> dict:
    """Normalise a template config with the same validators as content projects."""
    out: dict = {"builtin": bool(cfg.get("builtin", False))}
    try:
        if "duration_minutes" in cfg:
            if cfg["duration_minutes"] not in DURATION_CHOICES:
                raise AppError(f"duration_minutes phải là một trong {DURATION_CHOICES}")
            out["duration_minutes"] = cfg["duration_minutes"]
        if cfg.get("animation") is not None:
            out["animation"] = AnimationConfig(**cfg["animation"]).model_dump()
        if cfg.get("audio_layers") is not None:
            layers = [AudioLayerIn(**l) for l in cfg["audio_layers"]]
            if any(l.kind == "asset" for l in layers):
                raise AppError("Template chỉ chứa lớp âm thanh dạng generator (asset thuộc từng kênh)")
            out["audio_layers"] = [l.model_dump() for l in layers]
        if cfg.get("pomodoro") is not None:
            out["pomodoro"] = PomodoroConfig(**cfg["pomodoro"]).model_dump()
        if cfg.get("render_settings") is not None:
            rs = RenderSettings(**cfg["render_settings"]).model_dump()
            rs["overlay"].pop("font_asset_id", None)
            out["render_settings"] = rs
        if cfg.get("tags") is not None:
            out["tags"] = [str(t).strip()[:100] for t in cfg["tags"] if str(t).strip()][:30]
    except ValidationError as exc:
        raise AppError("Cấu hình template không hợp lệ: " + "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())) from exc
    return out


def create_template(db: Session, data: TemplateIn) -> TemplateOut:
    if data.channel_id is not None and db.get(Channel, data.channel_id) is None:
        raise NotFound(f"Không tìm thấy kênh #{data.channel_id}")
    cfg = validate_config({**data.config, "builtin": False})
    t = VideoTemplate(channel_id=data.channel_id, name=data.name, content_type=data.content_type, config=cfg)
    db.add(t)
    db.flush()
    activity.record(db, "template", f"Tạo template '{t.name}'", channel_id=data.channel_id)
    db.commit()
    return template_out(t)


def template_from_project(db: Session, p: ContentProject, name: str) -> TemplateOut:
    cfg = {
        "duration_minutes": p.duration_minutes,
        "animation": p.animation,
        "audio_layers": [l for l in (p.audio_layers or []) if l.get("kind") == "generator"],
        "pomodoro": p.pomodoro,
        "render_settings": p.render_settings,
        "tags": p.youtube_tags,
    }
    return create_template(db, TemplateIn(channel_id=p.channel_id, name=name, content_type=p.content_type,
                                          config={k: v for k, v in cfg.items() if v is not None}))


def update_template(db: Session, t: VideoTemplate, data: TemplateUpdate) -> TemplateOut:
    if data.name is not None:
        t.name = data.name
    if data.config is not None:
        t.config = validate_config({**data.config, "builtin": (t.config or {}).get("builtin", False)})
    activity.record(db, "template", f"Cập nhật template '{t.name}'", channel_id=t.channel_id)
    db.commit()
    return template_out(t)


def delete_template(db: Session, t: VideoTemplate) -> None:
    name, cid = t.name, t.channel_id
    db.delete(t)   # projects keep their own copy of the settings (template_id → NULL)
    activity.record(db, "template", f"Xóa template '{name}'", channel_id=cid)
    db.commit()
