"""Content Manager: per-channel content projects.

Rules:
  * every reference is checked against the project's channel (character must be owned by /
    granted to the channel — also enforced by a composite FK; assets must be the channel's or
    shared; templates/ideas must be shared or the channel's)
  * the character VERSION is pinned when the project is created → renders always use the same look
  * a fingerprint of everything that changes the rendered output blocks duplicating a video by
    only changing its title/description/tags (UNIQUE(channel_id, fingerprint))
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import storage
from app.core.config import get_settings
from app.models import (
    Asset,
    Channel,
    ChannelCharacter,
    Character,
    CharacterVersion,
    ContentIdea,
    ContentProject,
    Video,
    VideoJob,
    VideoTemplate,
)
from app.models.enums import (
    DURATION_CHOICES,
    AssetKind,
    IdeaStatus,
    JobStatus,
    ProductionStatus,
)
from app.render import ffmpeg as ff
from app.render import metadata as meta
from app.render.fonts import find_font
from app.render.scene import has_transparency
from app.render.thumbnail import render_thumbnail
from app.render.timeline import chapters, pomodoro_phases
from app.render.video import estimate_size_bytes
from app.schemas.content import (
    AnimationConfig,
    ContentCreate,
    ContentOut,
    ContentUpdate,
    JobBrief,
    MetadataOut,
    PomodoroConfig,
    RenderSettings,
    ValidationReport,
)
from app.services import activity
from app.services.asset_service import get_usable
from app.services.character_service import get_link
from app.services.errors import AppError, Conflict, NotFound

LOCKED_STATUSES = (ProductionStatus.QUEUED, ProductionStatus.RENDERING)


# ----------------------------------------------------------------- lookups
def get_project(db: Session, channel_id: int, project_id: int) -> ContentProject:
    p = db.scalar(select(ContentProject).where(ContentProject.id == project_id,
                                               ContentProject.channel_id == channel_id))
    if p is None:
        raise NotFound(f"Kênh #{channel_id} không có dự án nội dung #{project_id}")
    return p


def get_template(db: Session, channel_id: int, template_id: int) -> VideoTemplate:
    t = db.get(VideoTemplate, template_id)
    if t is None or (t.channel_id is not None and t.channel_id != channel_id):
        raise NotFound(f"Không tìm thấy template #{template_id} cho kênh này")
    return t


def pinned_version(db: Session, p: ContentProject) -> CharacterVersion | None:
    if p.character_version_id is None:
        return None
    return db.get(CharacterVersion, p.character_version_id)


def character_image(v: CharacterVersion | None) -> str | None:
    """Image used in renders: full-body first, then avatar."""
    if v is None:
        return None
    return v.full_body_image or v.avatar_image


# ----------------------------------------------------------------- output
def _job_brief(j: VideoJob | None) -> JobBrief | None:
    if j is None:
        return None
    return JobBrief(id=j.id, job_type=j.job_type.value, status=j.status.value, progress=j.progress,
                    step=j.step, error=j.error, created_at=j.created_at, finished_at=j.finished_at,
                    output_url=storage.media_url(j.output_path) if j.status == JobStatus.SUCCEEDED else None)


def project_out(db: Session, p: ContentProject) -> ContentOut:
    ch = db.get(Channel, p.channel_id)
    char = db.get(Character, p.character_id) if p.character_id else None
    ver = pinned_version(db, p)
    bg = None
    if p.background_asset_id:
        a = db.get(Asset, p.background_asset_id)
        bg = storage.media_url(a.file_path) if a else None
    latest = db.scalar(select(VideoJob).where(VideoJob.channel_id == p.channel_id,
                                              VideoJob.content_project_id == p.id)
                       .order_by(VideoJob.created_at.desc(), VideoJob.id.desc()).limit(1))
    videos = db.scalar(select(func.count()).select_from(Video).where(
        Video.channel_id == p.channel_id, Video.content_project_id == p.id)) or 0
    return ContentOut(
        id=p.id, channel_id=p.channel_id, channel_name=ch.name if ch else "?", title=p.title,
        content_type=p.content_type, character_id=p.character_id, character_name=char.name if char else None,
        character_version_id=p.character_version_id, character_version_no=ver.version_no if ver else None,
        character_current_version_id=char.current_version_id if char else None,
        theme=p.theme, script=p.script, setting=p.setting, background_asset_id=p.background_asset_id,
        background_url=bg, animation=p.animation, scene3d=p.scene3d, scene3d_model_url=_scene_model_url(db, p),
        audio_layers=p.audio_layers,
        duration_minutes=p.duration_minutes, pomodoro=p.pomodoro, render_settings=p.render_settings,
        youtube_title=p.youtube_title, youtube_description=p.youtube_description, youtube_tags=p.youtube_tags,
        thumbnail_url=storage.media_url(p.thumbnail_path), status=p.status, last_error=p.last_error,
        template_id=p.template_id, idea_id=p.idea_id, fingerprint=p.fingerprint, video_count=int(videos),
        latest_job=_job_brief(latest), created_at=p.created_at, updated_at=p.updated_at,
    )


def list_projects(db: Session, *, channel_id: int | None = None, status: ProductionStatus | None = None,
                  content_type: str | None = None, q: str | None = None) -> list[ContentOut]:
    stmt = select(ContentProject)
    if channel_id is not None:
        stmt = stmt.where(ContentProject.channel_id == channel_id)
    if status is not None:
        stmt = stmt.where(ContentProject.status == status)
    if content_type:
        stmt = stmt.where(ContentProject.content_type == content_type)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(ContentProject.title.ilike(like), ContentProject.youtube_title.ilike(like),
                              ContentProject.theme.ilike(like), ContentProject.setting.ilike(like)))
    rows = db.scalars(stmt.order_by(ContentProject.updated_at.desc(), ContentProject.id.desc())).all()
    return [project_out(db, p) for p in rows]


def _scene_model_url(db: Session, p: ContentProject) -> str | None:
    asset_id = ((p.scene3d or {}).get("character") or {}).get("asset_id")
    a = db.get(Asset, asset_id) if asset_id else None
    return storage.media_url(a.file_path) if a is not None else None


# ----------------------------------------------------------------- fingerprint
def compute_fingerprint(p: ContentProject) -> str:
    rs = p.render_settings or {}
    overlay = rs.get("overlay") or {}
    payload = {
        "type": p.content_type.value if hasattr(p.content_type, "value") else p.content_type,
        "theme": (p.theme or "").strip().lower(),
        "setting": (p.setting or "").strip().lower(),
        "background": p.background_asset_id,
        "character": [p.character_id, p.character_version_id],
        "animation": p.animation or {},
        "scene3d": p.scene3d or None,
        "audio": sorted(
            [l.get("kind"), l.get("asset_id"), l.get("generator"), round(float(l.get("volume", 1)), 2)]
            for l in (p.audio_layers or [])
        ),
        "duration": p.duration_minutes,
        "pomodoro": p.pomodoro,
        "overlay": [overlay.get("mode"), overlay.get("position"), overlay.get("color"),
                    overlay.get("font_asset_id"), overlay.get("labels") or {}],
        "chime": bool(rs.get("chime")),
        "format": [rs.get("resolution", "1920x1080"), rs.get("fps", 30)],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _ensure_unique(db: Session, p: ContentProject) -> None:
    p.fingerprint = compute_fingerprint(p)
    stmt = select(ContentProject).where(ContentProject.channel_id == p.channel_id,
                                        ContentProject.fingerprint == p.fingerprint)
    if p.id is not None:
        stmt = stmt.where(ContentProject.id != p.id)
    dup = db.scalar(stmt)
    if dup is not None:
        raise Conflict(
            f"Nội dung trùng với dự án #{dup.id} '{dup.title}' (chỉ khác tiêu đề/mô tả/tags). "
            "Hãy thay đổi bối cảnh, hình nền, âm thanh, nhân vật, hiệu ứng hoặc thời lượng để tạo video mới."
        )


# ----------------------------------------------------------------- validation of references
def _check_refs(db: Session, channel_id: int, *, background_asset_id: int | None, audio_layers: list[dict],
                render_settings: dict, scene3d: dict | None = None) -> None:
    model_id = ((scene3d or {}).get("character") or {}).get("asset_id")
    if model_id is not None:
        get_usable(db, channel_id, model_id, AssetKind.MODEL)
    if background_asset_id is not None:
        get_usable(db, channel_id, background_asset_id, AssetKind.IMAGE)
    for layer in audio_layers:
        if layer.get("kind") == "asset":
            get_usable(db, channel_id, layer["asset_id"], AssetKind.AUDIO)
    font_id = (render_settings.get("overlay") or {}).get("font_asset_id")
    if font_id is not None:
        get_usable(db, channel_id, font_id, AssetKind.FONT)


def _pin_character(db: Session, channel_id: int, character_id: int) -> tuple[int, int]:
    link = get_link(db, channel_id, character_id)   # 404 when not owned / not granted
    char = link.character
    if char.archived:
        raise AppError(f"Nhân vật '{char.name}' đã được lưu trữ, không dùng cho nội dung mới")
    if char.current_version_id is None:
        raise AppError(f"Nhân vật '{char.name}' chưa có phiên bản")
    return char.id, char.current_version_id


def _template_defaults(tpl: VideoTemplate) -> dict:
    cfg = tpl.config or {}
    out: dict = {}
    if cfg.get("duration_minutes") in DURATION_CHOICES:
        out["duration_minutes"] = cfg["duration_minutes"]
    if cfg.get("animation"):
        out["animation"] = AnimationConfig(**cfg["animation"]).model_dump()
    if cfg.get("audio_layers") is not None:
        out["audio_layers"] = cfg["audio_layers"]
    if cfg.get("pomodoro"):
        out["pomodoro"] = PomodoroConfig(**cfg["pomodoro"]).model_dump()
    if cfg.get("render_settings"):
        out["render_settings"] = RenderSettings(**cfg["render_settings"]).model_dump()
    if cfg.get("tags"):
        out["youtube_tags"] = list(cfg["tags"])
    return out


# ----------------------------------------------------------------- mutations
def create_project(db: Session, channel: Channel, data: ContentCreate) -> ContentProject:
    values = data.model_dump(exclude={"template_id", "idea_id"})
    if data.template_id is not None:
        tpl = get_template(db, channel.id, data.template_id)
        for k, v in _template_defaults(tpl).items():
            if k not in data.model_fields_set:
                values[k] = v
    if data.idea_id is not None:
        idea = db.get(ContentIdea, data.idea_id)
        if idea is None or idea.channel_id != channel.id:
            raise NotFound(f"Kênh không có ý tưởng #{data.idea_id}")
    _check_refs(db, channel.id, background_asset_id=values["background_asset_id"],
                audio_layers=values["audio_layers"], render_settings=values["render_settings"],
                scene3d=values.get("scene3d"))
    char_id = version_id = None
    if values.get("character_id") is not None:
        char_id, version_id = _pin_character(db, channel.id, values["character_id"])
    values.pop("character_id", None)
    p = ContentProject(channel_id=channel.id, template_id=data.template_id, idea_id=data.idea_id,
                       character_id=char_id, character_version_id=version_id, **values)
    _ensure_unique(db, p)
    db.add(p)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("Không thể tạo dự án (dữ liệu trùng hoặc tham chiếu không hợp lệ)") from exc
    if data.idea_id is not None:
        db.execute(update(ContentIdea).where(ContentIdea.id == data.idea_id).values(status=IdeaStatus.USED))
    activity.record(db, "content", f"Tạo dự án nội dung '{p.title}'", channel_id=channel.id,
                    details={"project_id": p.id})
    db.commit()
    return p


RENDER_FIELDS = {"content_type", "theme", "setting", "background_asset_id", "animation", "scene3d", "audio_layers",
                 "duration_minutes", "pomodoro", "render_settings", "character_id"}


def update_project(db: Session, p: ContentProject, data: ContentUpdate) -> ContentProject:
    if p.status in LOCKED_STATUSES:
        raise Conflict("Dự án đang trong hàng đợi / đang render. Hủy tác vụ render trước khi sửa.")
    changes = data.model_dump(exclude_unset=True, exclude={"clear_character", "clear_background", "clear_pomodoro",
                                                                         "clear_scene3d"})
    changes = {k: v for k, v in changes.items() if v is not None}
    before = compute_fingerprint(p)

    if data.clear_background:
        p.background_asset_id = None
        changes.pop("background_asset_id", None)
    if data.clear_scene3d:
        p.scene3d = None
        changes.pop("scene3d", None)
    if data.clear_pomodoro:
        p.pomodoro = None
        changes.pop("pomodoro", None)
    if data.clear_character:
        p.character_id = p.character_version_id = None
        changes.pop("character_id", None)

    _check_refs(db, p.channel_id,
                background_asset_id=changes.get("background_asset_id"),
                audio_layers=changes.get("audio_layers", []),
                render_settings=changes.get("render_settings", {}),
                scene3d=changes.get("scene3d"))
    if "character_id" in changes and changes["character_id"] != p.character_id:
        p.character_id, p.character_version_id = _pin_character(db, p.channel_id, changes.pop("character_id"))
    changes.pop("character_id", None)
    for k, v in changes.items():
        setattr(p, k, v)
    _ensure_unique(db, p)
    if p.fingerprint != before and p.status in (ProductionStatus.READY, ProductionStatus.RENDERED,
                                                 ProductionStatus.FAILED):
        p.status = ProductionStatus.DRAFT   # the rendered output no longer matches the configuration
    activity.record(db, "content", f"Cập nhật dự án '{p.title}'", channel_id=p.channel_id,
                    details={"project_id": p.id, "fields": sorted(data.model_fields_set)})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("Không thể lưu: tham chiếu không hợp lệ hoặc nội dung trùng") from exc
    return p


def sync_character_version(db: Session, p: ContentProject) -> ContentProject:
    if p.status in LOCKED_STATUSES:
        raise Conflict("Dự án đang render")
    if p.character_id is None:
        raise AppError("Dự án chưa chọn nhân vật")
    _, current = _pin_character(db, p.channel_id, p.character_id)
    if current == p.character_version_id:
        raise AppError("Dự án đã dùng phiên bản mới nhất của nhân vật")
    old = pinned_version(db, p)
    p.character_version_id = current
    _ensure_unique(db, p)
    if p.status in (ProductionStatus.READY, ProductionStatus.RENDERED, ProductionStatus.FAILED):
        p.status = ProductionStatus.DRAFT
    new = pinned_version(db, p)
    activity.record(db, "content", f"Dự án '{p.title}': nhân vật v{old.version_no if old else '?'} → "
                    f"v{new.version_no if new else '?'}", channel_id=p.channel_id)
    db.commit()
    return p


def delete_project(db: Session, p: ContentProject) -> None:
    if p.status in LOCKED_STATUSES:
        raise Conflict("Dự án đang trong hàng đợi / đang render. Hủy tác vụ trước khi xóa.")
    # keep rendered videos (they may be published): detach them from the project
    db.execute(update(Video).where(Video.channel_id == p.channel_id, Video.content_project_id == p.id)
               .values(content_project_id=None))
    title, cid = p.title, p.channel_id
    db.delete(p)
    activity.record(db, "content", f"Xóa dự án nội dung '{title}'", channel_id=cid)
    db.commit()


# ----------------------------------------------------------------- render readiness
def validate_for_render(db: Session, p: ContentProject) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        ff.ffmpeg_bin()
    except ff.FFmpegNotFound as exc:
        errors.append(str(exc))

    ch = db.get(Channel, p.channel_id)
    if ch is not None and not ch.enabled:
        warnings.append("Kênh đang tạm dừng: tác vụ render sẽ chờ tới khi bật lại kênh")

    if p.duration_minutes not in DURATION_CHOICES:
        errors.append(f"Thời lượng phải là một trong {DURATION_CHOICES} phút")

    if p.background_asset_id is None:
        errors.append("Chưa chọn hình nền (tải ảnh lên hoặc tạo ảnh nền ở mục Assets)")
    else:
        try:
            a = get_usable(db, p.channel_id, p.background_asset_id, AssetKind.IMAGE)
            if not storage.resolve(a.file_path).exists():
                errors.append(f"File hình nền '{a.name}' không còn trên ổ đĩa")
        except AppError as exc:
            errors.append(exc.message)

    if not p.audio_layers:
        errors.append("Chưa có lớp âm thanh nào")
    for layer in p.audio_layers or []:
        if layer.get("kind") == "asset":
            try:
                a = get_usable(db, p.channel_id, layer["asset_id"], AssetKind.AUDIO)
                if not storage.resolve(a.file_path).exists():
                    errors.append(f"File âm thanh '{a.name}' không còn trên ổ đĩa")
            except AppError as exc:
                errors.append(exc.message)

    if p.character_id is not None:
        link = db.scalar(select(ChannelCharacter).where(ChannelCharacter.channel_id == p.channel_id,
                                                        ChannelCharacter.character_id == p.character_id))
        if link is None:
            errors.append("Kênh không còn quyền dùng nhân vật đã chọn")
        v = pinned_version(db, p)
        img = character_image(v)
        if img is None:
            errors.append("Phiên bản nhân vật đã ghim chưa có ảnh toàn thân hoặc ảnh đại diện")
        else:
            try:
                path = storage.resolve(img)
                if not path.exists():
                    errors.append("File ảnh nhân vật không còn trên ổ đĩa")
                elif not has_transparency(path):
                    warnings.append("Ảnh nhân vật không có nền trong suốt (PNG alpha) — sẽ hiện thành khối chữ nhật")
            except Exception:  # noqa: BLE001
                errors.append("Không đọc được ảnh nhân vật")
        char = db.get(Character, p.character_id)
        if char and v and char.current_version_id != v.id:
            warnings.append(f"Nhân vật đã có phiên bản mới; dự án vẫn dùng v{v.version_no} để giữ nhất quán. "
                            "Bấm 'Dùng phiên bản mới nhất' nếu muốn cập nhật.")

    overlay = (p.render_settings or {}).get("overlay") or {}
    if overlay.get("mode") == "pomodoro" and not p.pomodoro:
        errors.append("Đồng hồ Pomodoro cần cấu hình Pomodoro (phút tập trung / nghỉ)")
    if overlay.get("mode", "none") != "none":
        font_ok = False
        if overlay.get("font_asset_id"):
            try:
                a = get_usable(db, p.channel_id, overlay["font_asset_id"], AssetKind.FONT)
                font_ok = storage.resolve(a.file_path).exists()
            except AppError as exc:
                errors.append(exc.message)
        else:
            font_ok = find_font() is not None
        if not font_ok:
            errors.append("Không có font cho đồng hồ: sudo apt install fonts-dejavu-core, hoặc chọn font asset")
        try:
            if not ff.has_filter("drawtext"):
                errors.append("FFmpeg không có filter drawtext (cần bản build có libfreetype)")
        except Exception:  # noqa: BLE001
            pass

    settings = get_settings()
    est = estimate_size_bytes(p.duration_minutes * 60, settings.render_max_bitrate_kbps,
                              settings.render_audio_bitrate_kbps)
    free = shutil.disk_usage(storage.storage_root()).free
    need = est + settings.min_free_disk_gb * 1024**3
    if free < need:
        errors.append(f"Không đủ dung lượng đĩa: cần ~{need / 1024**3:.1f} GB, còn {free / 1024**3:.1f} GB")

    if not p.youtube_title:
        warnings.append("Chưa có tiêu đề YouTube (bấm 'Tạo metadata')")
    return ValidationReport(ok=not errors, errors=errors, warnings=warnings)


def mark_ready(db: Session, p: ContentProject) -> ContentProject:
    if p.status in LOCKED_STATUSES:
        raise Conflict("Dự án đang render")
    report = validate_for_render(db, p)
    if not report.ok:
        raise AppError("Chưa thể đánh dấu sẵn sàng: " + "; ".join(report.errors))
    p.status = ProductionStatus.READY
    p.last_error = None
    activity.record(db, "content", f"Dự án '{p.title}' sẵn sàng render", channel_id=p.channel_id)
    db.commit()
    return p


# ----------------------------------------------------------------- metadata & thumbnail
def _attributions(db: Session, p: ContentProject) -> tuple[list[str], dict[int, str]]:
    ids = [l["asset_id"] for l in (p.audio_layers or []) if l.get("kind") == "asset"]
    if p.background_asset_id:
        ids.append(p.background_asset_id)
    assets = db.scalars(select(Asset).where(Asset.id.in_(ids))).all() if ids else []
    attributions = []
    for a in assets:
        if a.attribution:
            attributions.append(a.attribution)
        elif a.license_type.value in ("cc_by",):
            attributions.append(f"{a.name} — {a.license_source}")
    return attributions, {a.id: a.name for a in assets}


def build_metadata(db: Session, p: ContentProject) -> dict:
    ch = db.get(Channel, p.channel_id)
    lang = "vi" if (ch.language or "en").lower().startswith("vi") else "en"
    char = db.get(Character, p.character_id) if p.character_id else None
    pomo = p.pomodoro if ((p.render_settings or {}).get("overlay") or {}).get("mode") == "pomodoro" else None
    chaps = []
    if pomo:
        chaps = chapters(pomodoro_phases(p.duration_minutes * 60, pomo["focus_min"], pomo["short_break_min"],
                                         pomo["long_break_min"], pomo["cycles_before_long"]), lang)
    attributions, names = _attributions(db, p)
    sounds = meta.sound_names(p.audio_layers or [], names, lang)
    title = meta.make_title(p.content_type.value, p.duration_minutes, p.setting, p.theme, pomo, lang,
                            char.name if char else None)
    description = meta.make_description(
        content_type=p.content_type.value, duration_min=p.duration_minutes, setting=p.setting, theme=p.theme,
        pomodoro=pomo, chapters=chaps, sounds=sounds, attributions=attributions,
        channel_description=ch.description or "", lang=lang, character=char.name if char else None,
        script=p.script)
    tags = meta.make_tags(p.content_type.value, p.setting, p.theme, list(p.youtube_tags or []),
                          list(ch.topics or []), sounds, lang)
    return {"youtube_title": title, "youtube_description": description, "youtube_tags": tags}


def generate_metadata(db: Session, p: ContentProject, apply: bool = True) -> MetadataOut:
    m = build_metadata(db, p)
    if apply:
        if p.status in LOCKED_STATUSES:
            raise Conflict("Dự án đang render")
        p.youtube_title, p.youtube_description, p.youtube_tags = (
            m["youtube_title"], m["youtube_description"], m["youtube_tags"])
        activity.record(db, "content", f"Tạo metadata YouTube cho '{p.title}'", channel_id=p.channel_id)
        db.commit()
    return MetadataOut(**m, applied=apply)


def generate_thumbnail(db: Session, p: ContentProject) -> ContentProject:
    if p.background_asset_id is None:
        raise AppError("Cần chọn hình nền trước khi tạo thumbnail")
    bg = get_usable(db, p.channel_id, p.background_asset_id, AssetKind.IMAGE)
    char_img = character_image(pinned_version(db, p))
    ch = db.get(Channel, p.channel_id)
    lang = "vi" if (ch.language or "en").lower().startswith("vi") else "en"
    palette = (ch.visual_style or {}).get("palette") or []
    font = None
    font_id = ((p.render_settings or {}).get("overlay") or {}).get("font_asset_id")
    if font_id:
        fa = db.get(Asset, font_id)
        font = storage.resolve(fa.file_path) if fa else None
    tmp = storage.tmp_dir() / f"thumb-{p.id}.jpg"
    render_thumbnail(tmp, background=storage.resolve(bg.file_path), title=p.youtube_title or p.title,
                     badge=meta.duration_label(p.duration_minutes, lang).upper(),
                     character=storage.resolve(char_img) if char_img else None,
                     accent=palette[1] if len(palette) > 1 else (palette[0] if palette else "#E3A86B"),
                     font_path=font)
    data = tmp.read_bytes()
    tmp.unlink(missing_ok=True)
    info = storage.save_image(data, Path("channels") / str(p.channel_id) / "content" / str(p.id))
    p.thumbnail_path = info["path"]
    activity.record(db, "content", f"Tạo thumbnail cho '{p.title}'", channel_id=p.channel_id)
    db.commit()
    return p


def upload_thumbnail(db: Session, p: ContentProject, data: bytes) -> ContentProject:
    if len(data) > 2 * 1024 * 1024:
        raise AppError("YouTube giới hạn thumbnail 2 MB")
    info = storage.save_image(data, Path("channels") / str(p.channel_id) / "content" / str(p.id))
    if info["width"] < 640:
        raise AppError("Thumbnail nên rộng tối thiểu 640px (khuyến nghị 1280x720)")
    p.thumbnail_path = info["path"]
    activity.record(db, "content", f"Tải thumbnail cho '{p.title}'", channel_id=p.channel_id)
    db.commit()
    return p

