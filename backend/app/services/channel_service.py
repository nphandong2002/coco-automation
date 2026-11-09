"""Channel Manager business logic."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core import storage
from app.models import (
    AnalyticsDaily,
    Channel,
    ChannelCharacter,
    Character,
    CharacterVersion,
    ContentProject,
    PublishingJob,
    Video,
    VideoJob,
)
from app.models.enums import JobStatus
from app.schemas.channel import ChannelClone, ChannelCreate, ChannelOut, ChannelSummary, ChannelUpdate
from app.services import activity
from app.services.errors import Conflict, NotFound


def _query():
    return select(Channel).options(selectinload(Channel.credential))


def get_channel(db: Session, channel_id: int) -> Channel:
    ch = db.scalar(_query().where(Channel.id == channel_id))
    if ch is None:
        raise NotFound(f"Không tìm thấy kênh #{channel_id}")
    return ch


def to_out(ch: Channel, character_count: int = 0) -> ChannelOut:
    out = ChannelOut.model_validate(ch)
    out.avatar_url = storage.media_url(ch.avatar_path)
    out.banner_url = storage.media_url(ch.banner_path)
    out.youtube_channel_title = ch.credential.youtube_channel_title if ch.credential else None
    out.character_count = character_count
    return out


def list_channels(db: Session) -> list[ChannelOut]:
    channels = db.scalars(_query().order_by(Channel.created_at)).all()
    counts = dict(
        db.execute(
            select(ChannelCharacter.channel_id, func.count()).group_by(ChannelCharacter.channel_id)
        ).all()
    )
    return [to_out(c, counts.get(c.id, 0)) for c in channels]


def channel_out(db: Session, ch: Channel) -> ChannelOut:
    n = db.scalar(select(func.count()).where(ChannelCharacter.channel_id == ch.id)) or 0
    return to_out(ch, n)


def _ensure_code_free(db: Session, code: str) -> None:
    if db.scalar(select(Channel.id).where(Channel.code == code)):
        raise Conflict(f"Mã kênh '{code}' đã tồn tại")


def create_channel(db: Session, data: ChannelCreate) -> Channel:
    _ensure_code_free(db, data.code)
    ch = Channel(**data.model_dump())
    db.add(ch)
    db.flush()
    activity.record(db, "channel", f"Tạo kênh '{ch.name}'", channel_id=ch.id)
    db.commit()
    return get_channel(db, ch.id)


def update_channel(db: Session, ch: Channel, data: ChannelUpdate) -> Channel:
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in changes.items():
        setattr(ch, k, v)
    if changes:
        activity.record(
            db, "channel", f"Cập nhật kênh '{ch.name}'", channel_id=ch.id,
            details={"fields": sorted(changes)},
        )
    db.commit()
    return get_channel(db, ch.id)


def set_enabled(db: Session, ch: Channel, enabled: bool) -> Channel:
    ch.enabled = enabled
    activity.record(
        db, "channel", f"{'Bật' if enabled else 'Tạm dừng'} kênh '{ch.name}'", channel_id=ch.id
    )
    db.commit()
    return get_channel(db, ch.id)


def clear_error(db: Session, ch: Channel) -> Channel:
    ch.last_error = None
    ch.last_error_at = None
    activity.record(db, "channel", f"Xóa trạng thái lỗi của kênh '{ch.name}'", channel_id=ch.id)
    db.commit()
    return get_channel(db, ch.id)


def delete_channel(db: Session, ch: Channel, confirm_code: str) -> None:
    if confirm_code != ch.code:
        raise Conflict("Mã xác nhận không khớp. Nhập đúng mã kênh để xóa.")
    channel_id, name = ch.id, ch.name
    try:
        db.delete(ch)
        activity.record(db, "channel", f"Xóa kênh '{name}' (#{channel_id})")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(
            "Không thể xóa: nhân vật của kênh này đang được kênh khác sử dụng trong nội dung. "
            "Hãy gỡ nội dung đó hoặc thu hồi quyền trước."
        ) from exc
    storage.remove_channel_files(channel_id)


def save_brand_image(db: Session, ch: Channel, kind: str, data: bytes) -> Channel:
    info = storage.save_image(data, Path("channels") / str(ch.id) / "brand")
    if kind == "avatar":
        ch.avatar_path = info["path"]
    else:
        ch.banner_path = info["path"]
    activity.record(db, "channel", f"Cập nhật {kind} cho kênh '{ch.name}'", channel_id=ch.id)
    db.commit()
    return get_channel(db, ch.id)


def clone_channel(db: Session, src: Channel, data: ChannelClone) -> Channel:
    """Copy brand configuration (and optionally OWNED characters) into a new channel.

    Never copied: YouTube credentials, videos, analytics, and characters merely
    GRANTED by another channel (permission belongs to the owner).
    """
    _ensure_code_free(db, data.code)
    new = Channel(
        code=data.code,
        name=data.name,
        description=src.description,
        language=src.language,
        target_country=src.target_country,
        topics=list(src.topics),
        visual_style=dict(src.visual_style),
        audio_style=dict(src.audio_style),
        publish_schedule=dict(src.publish_schedule),
        cloned_from_id=src.id,
    )
    db.add(new)
    db.flush()
    brand_dir = Path("channels") / str(new.id) / "brand"
    if src.avatar_path:
        new.avatar_path = storage.copy_file(src.avatar_path, brand_dir)
    if src.banner_path:
        new.banner_path = storage.copy_file(src.banner_path, brand_dir)

    copied = 0
    if data.include_characters:
        links = db.scalars(
            select(ChannelCharacter)
            .where(ChannelCharacter.channel_id == src.id, ChannelCharacter.is_owner.is_(True))
            .options(selectinload(ChannelCharacter.character).selectinload(Character.current_version))
        ).all()
        for link in links:
            _clone_character(db, link, new.id)
            copied += 1

    activity.record(
        db, "channel", f"Sao chép kênh '{src.name}' → '{new.name}' ({copied} nhân vật)",
        channel_id=new.id, details={"source_channel_id": src.id},
    )
    db.commit()
    return get_channel(db, new.id)


def _clone_character(db: Session, link: ChannelCharacter, new_channel_id: int) -> None:
    src_char = link.character
    cv = src_char.current_version
    char = Character(channel_id=new_channel_id, name=src_char.name, species=src_char.species,
                     archived=src_char.archived)
    db.add(char)
    db.flush()
    dst = Path("channels") / str(new_channel_id) / "characters" / str(char.id)

    def cp(p: str | None) -> str | None:
        return storage.copy_file(p, dst) if p else None

    version = CharacterVersion(
        character_id=char.id,
        version_no=1,
        appearance=cv.appearance if cv else "",
        art_style=cv.art_style if cv else "",
        primary_colors=list(cv.primary_colors) if cv else [],
        outfit=cv.outfit if cv else "",
        personality=cv.personality if cv else "",
        usual_settings=list(cv.usual_settings) if cv else [],
        allowed_animations=list(cv.allowed_animations) if cv else [],
        expressions=[{"name": e["name"], "image": cp(e["image"])} for e in (cv.expressions if cv else [])],
        avatar_image=cp(cv.avatar_image) if cv else None,
        full_body_image=cp(cv.full_body_image) if cv else None,
        reference_images=[cp(r) for r in (cv.reference_images if cv else [])],
        change_note=f"Sao chép từ nhân vật #{src_char.id} v{cv.version_no if cv else 0}",
    )
    db.add(version)
    db.flush()
    char.current_version_id = version.id
    db.add(ChannelCharacter(channel_id=new_channel_id, character_id=char.id,
                            role=link.role, is_owner=True))
    db.flush()


def channel_summary(db: Session, ch: Channel) -> ChannelSummary:
    cid = ch.id

    def count(stmt) -> int:  # noqa: ANN001
        return int(db.scalar(stmt) or 0)

    return ChannelSummary(
        characters_owned=count(select(func.count()).select_from(Character).where(Character.channel_id == cid)),
        characters_granted=count(
            select(func.count()).select_from(ChannelCharacter)
            .where(ChannelCharacter.channel_id == cid, ChannelCharacter.is_owner.is_(False))
        ),
        content_projects=count(select(func.count()).select_from(ContentProject).where(ContentProject.channel_id == cid)),
        videos=count(select(func.count()).select_from(Video).where(Video.channel_id == cid)),
        render_jobs_active=count(
            select(func.count()).select_from(VideoJob).where(
                VideoJob.channel_id == cid, VideoJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])
            )
        ),
        publishing_jobs_pending=count(
            select(func.count()).select_from(PublishingJob).where(
                PublishingJob.channel_id == cid,
                PublishingJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        ),
        analytics_days_synced=count(
            select(func.count()).select_from(AnalyticsDaily).where(AnalyticsDaily.channel_id == cid)
        ),
    )
