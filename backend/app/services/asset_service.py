"""Asset Manager: images / audio / video / fonts with MANDATORY licence information.

Scope: an asset belongs to one channel (channel_id) or to the shared library (NULL).
A channel may only use its own assets and shared assets — never another channel's.
"""
from __future__ import annotations

import random
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, ImageFont, UnidentifiedImageError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import storage
from app.core.config import get_settings
from app.models import Asset, Channel, ContentProject
from app.models.enums import AssetKind, AssetSource, LicenseType
from app.render import scene
from app.render.probe import ProbeError, probe
from app.schemas.asset import AssetOut, AssetUpdate, BackgroundGenerate, clean_tags
from app.services import activity
from app.services.errors import AppError, Conflict, NotFound

EXTENSIONS: dict[str, tuple[AssetKind, str]] = {
    "png": (AssetKind.IMAGE, "image/png"), "jpg": (AssetKind.IMAGE, "image/jpeg"),
    "jpeg": (AssetKind.IMAGE, "image/jpeg"), "webp": (AssetKind.IMAGE, "image/webp"),
    "mp3": (AssetKind.AUDIO, "audio/mpeg"), "wav": (AssetKind.AUDIO, "audio/wav"),
    "flac": (AssetKind.AUDIO, "audio/flac"), "ogg": (AssetKind.AUDIO, "audio/ogg"),
    "opus": (AssetKind.AUDIO, "audio/opus"), "m4a": (AssetKind.AUDIO, "audio/mp4"),
    "aac": (AssetKind.AUDIO, "audio/aac"),
    "mp4": (AssetKind.VIDEO, "video/mp4"), "mov": (AssetKind.VIDEO, "video/quicktime"),
    "webm": (AssetKind.VIDEO, "video/webm"), "mkv": (AssetKind.VIDEO, "video/x-matroska"),
    "ttf": (AssetKind.FONT, "font/ttf"), "otf": (AssetKind.FONT, "font/otf"),
}
GENERATOR_SOURCE = "Coco Automation – procedural generator (owned)"


# ----------------------------------------------------------------- helpers
def _scope_dir(channel_id: int | None, kind: AssetKind) -> Path:
    base = Path("channels") / str(channel_id) / "assets" if channel_id else Path("shared") / "assets"
    return base / kind.value


def validate_license(license_type: LicenseType, source: str, attribution: str) -> None:
    source, attribution = source.strip(), attribution.strip()
    if license_type != LicenseType.OWNED and not source:
        raise AppError("Cần ghi nguồn giấy phép (URL hoặc mô tả nơi mua / giấy phép) cho tài nguyên không tự sở hữu")
    if license_type == LicenseType.CC_BY and not attribution:
        raise AppError("Giấy phép CC BY bắt buộc có dòng ghi công (attribution)")


def asset_out(a: Asset, channel_name: str | None = None) -> AssetOut:
    return AssetOut(
        id=a.id, channel_id=a.channel_id, channel_name=channel_name, kind=a.kind, name=a.name,
        url=storage.media_url(a.file_path) or "", sha256=a.sha256, size_bytes=a.size_bytes,
        mime_type=a.mime_type, duration_sec=a.duration_sec, width=a.width, height=a.height,
        license_type=a.license_type, license_source=a.license_source, attribution=a.attribution,
        tags=a.tags, source=a.source, meta=a.meta, created_at=a.created_at,
    )


def get_asset(db: Session, asset_id: int) -> Asset:
    a = db.get(Asset, asset_id)
    if a is None:
        raise NotFound(f"Không tìm thấy tài nguyên #{asset_id}")
    return a


def get_usable(db: Session, channel_id: int, asset_id: int, kind: AssetKind | None = None) -> Asset:
    """Asset that `channel_id` may use: its own or shared. Same 404 otherwise (no leak)."""
    a = db.get(Asset, asset_id)
    if a is None or (a.channel_id is not None and a.channel_id != channel_id):
        raise NotFound(f"Kênh #{channel_id} không có quyền dùng tài nguyên #{asset_id}")
    if kind is not None and a.kind != kind:
        raise AppError(f"Tài nguyên #{asset_id} là {a.kind.value}, cần {kind.value}")
    return a


def list_assets(db: Session, *, scope: str = "all", channel_id: int | None = None,
                kind: AssetKind | None = None, q: str | None = None) -> list[AssetOut]:
    stmt = select(Asset, Channel.name).outerjoin(Channel, Channel.id == Asset.channel_id)
    if scope == "shared":
        stmt = stmt.where(Asset.channel_id.is_(None))
    elif scope == "channel":
        if channel_id is None:
            raise AppError("Cần channel_id khi scope=channel")
        stmt = stmt.where(Asset.channel_id == channel_id)
    elif scope == "usable":
        if channel_id is None:
            raise AppError("Cần channel_id khi scope=usable")
        stmt = stmt.where(or_(Asset.channel_id == channel_id, Asset.channel_id.is_(None)))
    if kind is not None:
        stmt = stmt.where(Asset.kind == kind)
    if q:
        stmt = stmt.where(Asset.name.ilike(f"%{q.strip()}%"))
    rows = db.execute(stmt.order_by(Asset.created_at.desc(), Asset.id.desc())).all()
    return [asset_out(a, name) for a, name in rows]


def _inspect(kind: AssetKind, path: Path) -> dict:
    """Validate the stored file really is what its extension says. Returns metadata fields."""
    if kind == AssetKind.IMAGE:
        try:
            with Image.open(path) as im:
                im.verify()
            with Image.open(path) as im:
                return {"width": im.width, "height": im.height,
                        "meta": {"format": im.format, "mode": im.mode,
                                 "has_alpha": scene.has_transparency(path)}}
        except (UnidentifiedImageError, OSError) as exc:
            raise AppError("File không phải ảnh hợp lệ") from exc
    if kind == AssetKind.FONT:
        try:
            font = ImageFont.truetype(str(path), 24)
            return {"meta": {"family": " ".join(x for x in font.getname() if x)}}
        except OSError as exc:
            raise AppError("File font không hợp lệ (cần TTF/OTF)") from exc
    try:
        info = probe(path)
    except (ProbeError, FileNotFoundError, OSError) as exc:
        raise AppError(f"Không đọc được file media: {exc}") from exc
    except Exception as exc:  # FFmpeg missing etc.
        raise AppError(f"Không kiểm tra được media ({exc}). Cài ffmpeg trước khi tải audio/video.") from exc
    if kind == AssetKind.AUDIO and not info.get("audio"):
        raise AppError("File không có luồng âm thanh")
    if kind == AssetKind.VIDEO and not info.get("video"):
        raise AppError("File không có luồng hình ảnh")
    v = info.get("video") or {}
    return {"duration_sec": info.get("duration"), "width": v.get("width"), "height": v.get("height"),
            "meta": {"audio": info.get("audio"), "video": info.get("video"), "format": info.get("format_name")}}


def _ensure_channel(db: Session, channel_id: int | None) -> str | None:
    if channel_id is None:
        return None
    ch = db.get(Channel, channel_id)
    if ch is None:
        raise NotFound(f"Không tìm thấy kênh #{channel_id}")
    return ch.name


def _duplicate(db: Session, channel_id: int | None, sha: str) -> Asset | None:
    stmt = select(Asset).where(Asset.sha256 == sha)
    stmt = stmt.where(Asset.channel_id.is_(None) if channel_id is None else Asset.channel_id == channel_id)
    return db.scalar(stmt)


def create_from_upload(db: Session, upload: UploadFile, *, channel_id: int | None, name: str,
                       license_type: LicenseType, license_source: str, attribution: str,
                       tags: list[str]) -> AssetOut:
    validate_license(license_type, license_source, attribution)
    ch_name = _ensure_channel(db, channel_id)
    filename = upload.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in EXTENSIONS:
        raise AppError(f"Định dạng '.{ext}' không hỗ trợ. Cho phép: {', '.join(sorted(EXTENSIONS))}")
    kind, mime = EXTENSIONS[ext]
    limit = get_settings().max_upload_mb if kind == AssetKind.IMAGE else get_settings().max_asset_upload_mb
    info = storage.save_stream(upload.file, _scope_dir(channel_id, kind), "jpg" if ext == "jpeg" else ext,
                               limit * 1024 * 1024)
    dup = _duplicate(db, channel_id, info["sha256"])
    if dup is not None:
        raise Conflict(f"Tài nguyên này đã có trong thư viện: #{dup.id} '{dup.name}'")
    try:
        details = _inspect(kind, info["abs_path"])
    except AppError:
        storage.delete_file(info["path"])
        raise
    asset = Asset(
        channel_id=channel_id, kind=kind, name=(name.strip() or Path(filename).stem)[:200],
        file_path=info["path"], sha256=info["sha256"], size_bytes=info["size"], mime_type=mime,
        duration_sec=details.get("duration_sec"), width=details.get("width"), height=details.get("height"),
        license_type=license_type, license_source=license_source.strip(), attribution=attribution.strip(),
        tags=clean_tags(tags), source=AssetSource.UPLOAD, meta=details.get("meta") or {},
    )
    db.add(asset)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("Tài nguyên này đã có trong thư viện") from exc
    activity.record(db, "asset", f"Tải lên {kind.value} '{asset.name}' ({license_type.value})",
                    channel_id=channel_id, details={"asset_id": asset.id})
    db.commit()
    return asset_out(asset, ch_name)


def generate_background(db: Session, data: BackgroundGenerate) -> AssetOut:
    if data.style not in scene.BACKGROUND_STYLES:
        raise AppError(f"style phải là một trong: {', '.join(scene.BACKGROUND_STYLES)}")
    ch_name = _ensure_channel(db, data.channel_id)
    palette = data.palette
    if palette is None and data.channel_id is not None:
        ch = db.get(Channel, data.channel_id)
        palette = [c for c in (ch.visual_style or {}).get("palette", []) if isinstance(c, str)] or None
    seed = data.seed if data.seed is not None else random.randint(1, 2_000_000_000)
    tmp = storage.tmp_dir() / f"bg-{seed}-{random.randint(0, 1 << 30)}.png"
    scene.generate_background(tmp, 1920, 1080, data.style, palette, seed)
    info = storage.save_file(tmp, _scope_dir(data.channel_id, AssetKind.IMAGE), "png")
    dup = _duplicate(db, data.channel_id, info["sha256"])
    if dup is not None:
        return asset_out(dup, ch_name)
    asset = Asset(
        channel_id=data.channel_id, kind=AssetKind.IMAGE,
        name=data.name.strip() or f"{scene.BACKGROUND_STYLES[data.style]} #{seed}",
        file_path=info["path"], sha256=info["sha256"], size_bytes=info["size"], mime_type="image/png",
        width=1920, height=1080, license_type=LicenseType.OWNED, license_source=GENERATOR_SOURCE,
        attribution="", tags=clean_tags([*data.tags, "generated", data.style.replace("_", " ")]),
        source=AssetSource.GENERATED,
        meta={"generator": "background", "style": data.style, "palette": palette, "seed": seed},
    )
    db.add(asset)
    db.flush()
    activity.record(db, "asset", f"Tạo ảnh nền '{asset.name}'", channel_id=data.channel_id,
                    details={"asset_id": asset.id})
    db.commit()
    return asset_out(asset, ch_name)


def update_asset(db: Session, asset: Asset, data: AssetUpdate) -> AssetOut:
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    lt = changes.get("license_type", asset.license_type)
    validate_license(lt, changes.get("license_source", asset.license_source),
                     changes.get("attribution", asset.attribution))
    if asset.source == AssetSource.GENERATED and "license_type" in changes and lt != LicenseType.OWNED:
        raise AppError("Tài nguyên do hệ thống tạo luôn thuộc sở hữu của bạn (owned)")
    for k, v in changes.items():
        setattr(asset, k, v)
    activity.record(db, "asset", f"Cập nhật tài nguyên '{asset.name}'", channel_id=asset.channel_id,
                    details={"asset_id": asset.id, "fields": sorted(changes)})
    db.commit()
    ch_name = db.get(Channel, asset.channel_id).name if asset.channel_id else None
    return asset_out(asset, ch_name)


def usages(db: Session, asset: Asset) -> list[dict]:
    """Content projects that reference the asset (background, audio layer, font)."""
    out = []
    asset_id = asset.id
    stmt = select(ContentProject)
    if asset.channel_id is not None:  # a channel asset can only be used by that channel
        stmt = stmt.where(ContentProject.channel_id == asset.channel_id)
    for p in db.scalars(stmt).all():
        used = p.background_asset_id == asset_id
        used = used or any(l.get("asset_id") == asset_id for l in (p.audio_layers or []))
        used = used or ((p.render_settings or {}).get("overlay") or {}).get("font_asset_id") == asset_id
        if used:
            out.append({"project_id": p.id, "channel_id": p.channel_id, "title": p.title})
    return out


def delete_asset(db: Session, asset: Asset) -> None:
    used = usages(db, asset)
    if used:
        titles = ", ".join(f"'{u['title']}'" for u in used[:5])
        raise Conflict(f"Tài nguyên đang được dùng trong {len(used)} dự án ({titles}). Gỡ khỏi dự án trước khi xóa.")
    path, name, cid = asset.file_path, asset.name, asset.channel_id
    db.delete(asset)
    activity.record(db, "asset", f"Xóa tài nguyên '{name}'", channel_id=cid)
    db.commit()
    still = db.scalar(select(func.count()).select_from(Asset).where(Asset.file_path == path)) or 0
    if not still:
        storage.delete_file(path)
