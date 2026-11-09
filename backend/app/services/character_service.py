"""Character Manager business logic.

Rules enforced here (and partly by DB constraints):
  * A character is owned by one channel; only the owner can modify it.
  * Visual identity is versioned: every visual change creates a NEW immutable
    CharacterVersion. Old versions are never edited, so content pinned to a
    version keeps exactly the same look.
  * Another channel can use a character only after an explicit grant.
  * One PRIMARY character per channel.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core import storage
from app.models import Channel, ChannelCharacter, Character, CharacterVersion
from app.models.enums import CharacterRole
from app.schemas.character import (
    CharacterCreate,
    CharacterOut,
    CharacterUpdate,
    GrantCreate,
    ShareInfo,
    VersionCreate,
    VersionOut,
)
from app.services import activity
from app.services.errors import AppError, Conflict, Forbidden, NotFound

VISUAL_FIELDS = (
    "appearance",
    "art_style",
    "primary_colors",
    "outfit",
    "personality",
    "usual_settings",
    "allowed_animations",
)
IMAGE_SLOTS = ("avatar", "full_body", "reference", "expression")
MAX_REFERENCE_IMAGES = 30


# ----------------------------------------------------------------- lookups
def _link_query():
    return select(ChannelCharacter).options(
        selectinload(ChannelCharacter.character).selectinload(Character.current_version),
        selectinload(ChannelCharacter.character).selectinload(Character.owner_channel),
        selectinload(ChannelCharacter.character)
        .selectinload(Character.links)
        .selectinload(ChannelCharacter.channel),
    )


def get_link(db: Session, channel_id: int, character_id: int) -> ChannelCharacter:
    link = db.scalar(
        _link_query().where(
            ChannelCharacter.channel_id == channel_id, ChannelCharacter.character_id == character_id
        )
    )
    if link is None:
        # Deliberately the same message whether the character exists or not:
        # a channel must not learn about other channels' characters.
        raise NotFound(f"Kênh #{channel_id} không có quyền dùng nhân vật #{character_id}")
    return link


def require_owner(link: ChannelCharacter) -> Character:
    if not link.is_owner:
        raise Forbidden("Chỉ kênh sở hữu mới được chỉnh sửa nhân vật này")
    return link.character


# ----------------------------------------------------------------- output
def version_out(v: CharacterVersion, current_id: int | None) -> VersionOut:
    return VersionOut(
        id=v.id,
        version_no=v.version_no,
        appearance=v.appearance,
        art_style=v.art_style,
        primary_colors=v.primary_colors,
        outfit=v.outfit,
        personality=v.personality,
        usual_settings=v.usual_settings,
        allowed_animations=v.allowed_animations,
        expressions=[
            {"name": e["name"], "image": e["image"], "image_url": storage.media_url(e["image"])}
            for e in v.expressions
        ],
        avatar_url=storage.media_url(v.avatar_image),
        full_body_url=storage.media_url(v.full_body_image),
        reference_images=[{"path": p, "url": storage.media_url(p)} for p in v.reference_images],
        change_note=v.change_note,
        created_at=v.created_at,
        is_current=v.id == current_id,
    )


def character_out(db: Session, link: ChannelCharacter) -> CharacterOut:
    c = link.character
    version_count = len(db.scalars(
        select(CharacterVersion.id).where(CharacterVersion.character_id == c.id)
    ).all())
    shared = [
        ShareInfo(channel_id=l.channel_id, channel_name=l.channel.name, role=l.role, granted_at=l.granted_at)
        for l in c.links
        if not l.is_owner
    ]
    return CharacterOut(
        id=c.id,
        name=c.name,
        species=c.species,
        archived=c.archived,
        owner_channel_id=c.channel_id,
        owner_channel_name=c.owner_channel.name,
        channel_id=link.channel_id,
        role=link.role,
        is_owner=link.is_owner,
        version_count=version_count,
        current_version=version_out(c.current_version, c.current_version_id) if c.current_version else None,
        shared_with=shared if link.is_owner else [],
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def list_for_channel(db: Session, channel_id: int, include_archived: bool = True) -> list[CharacterOut]:
    links = db.scalars(
        _link_query().where(ChannelCharacter.channel_id == channel_id).order_by(ChannelCharacter.id)
    ).all()
    out = [character_out(db, l) for l in links if include_archived or not l.character.archived]
    # primary first
    out.sort(key=lambda c: (c.role != CharacterRole.PRIMARY, not c.is_owner, c.name.lower()))
    return out


def list_all_owned(db: Session) -> list[CharacterOut]:
    """Every character seen from its OWNER channel (for the global Characters page)."""
    links = db.scalars(
        _link_query().where(ChannelCharacter.is_owner.is_(True)).order_by(ChannelCharacter.channel_id)
    ).all()
    return [character_out(db, l) for l in links]


# ----------------------------------------------------------------- mutations
def _set_role(db: Session, channel_id: int, link: ChannelCharacter, role: CharacterRole) -> None:
    if role == CharacterRole.PRIMARY:
        db.execute(
            update(ChannelCharacter)
            .where(
                ChannelCharacter.channel_id == channel_id,
                ChannelCharacter.role == CharacterRole.PRIMARY,
                ChannelCharacter.id != (link.id or -1),
            )
            .values(role=CharacterRole.SECONDARY)
        )
        db.flush()
    link.role = role


def create_character(db: Session, channel: Channel, data: CharacterCreate) -> ChannelCharacter:
    if db.scalar(select(Character.id).where(Character.channel_id == channel.id, Character.name == data.name)):
        raise Conflict(f"Kênh đã có nhân vật tên '{data.name}'")
    char = Character(channel_id=channel.id, name=data.name, species=data.species)
    db.add(char)
    db.flush()
    fields = {f: getattr(data, f) for f in VISUAL_FIELDS if getattr(data, f) is not None}
    v = CharacterVersion(character_id=char.id, version_no=1, change_note="Khởi tạo", **fields)
    db.add(v)
    db.flush()
    char.current_version_id = v.id
    link = ChannelCharacter(channel_id=channel.id, character_id=char.id, is_owner=True,
                            role=CharacterRole.SECONDARY)
    db.add(link)
    db.flush()
    _set_role(db, channel.id, link, data.role)
    activity.record(db, "character", f"Tạo nhân vật '{char.name}'", channel_id=channel.id,
                    details={"character_id": char.id})
    db.commit()
    return get_link(db, channel.id, char.id)


def update_character(db: Session, link: ChannelCharacter, data: CharacterUpdate) -> ChannelCharacter:
    char = require_owner(link)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in changes and changes["name"] != char.name:
        dup = db.scalar(select(Character.id).where(
            Character.channel_id == char.channel_id, Character.name == changes["name"]))
        if dup:
            raise Conflict(f"Kênh đã có nhân vật tên '{changes['name']}'")
    for k, v in changes.items():
        setattr(char, k, v)
    activity.record(db, "character", f"Cập nhật thông tin nhân vật '{char.name}'",
                    channel_id=link.channel_id, details={"character_id": char.id, "fields": sorted(changes)})
    db.commit()
    return get_link(db, link.channel_id, char.id)


def _new_version_from_current(db: Session, char: Character, note: str, **overrides) -> CharacterVersion:
    cur = char.current_version
    base = {
        "appearance": cur.appearance if cur else "",
        "art_style": cur.art_style if cur else "",
        "primary_colors": list(cur.primary_colors) if cur else [],
        "outfit": cur.outfit if cur else "",
        "personality": cur.personality if cur else "",
        "usual_settings": list(cur.usual_settings) if cur else [],
        "allowed_animations": list(cur.allowed_animations) if cur else [],
        "expressions": [dict(e) for e in cur.expressions] if cur else [],
        "avatar_image": cur.avatar_image if cur else None,
        "full_body_image": cur.full_body_image if cur else None,
        "reference_images": list(cur.reference_images) if cur else [],
    }
    new_values = {**base, **overrides}
    if cur is not None and new_values == base:
        raise AppError("Không có thay đổi nào so với phiên bản hiện tại")
    last_no = db.scalar(
        select(CharacterVersion.version_no)
        .where(CharacterVersion.character_id == char.id)
        .order_by(CharacterVersion.version_no.desc())
        .limit(1)
    ) or 0
    v = CharacterVersion(character_id=char.id, version_no=last_no + 1, change_note=note, **new_values)
    db.add(v)
    db.flush()
    char.current_version_id = v.id
    char.current_version = v
    return v


def create_version(db: Session, link: ChannelCharacter, data: VersionCreate) -> ChannelCharacter:
    char = require_owner(link)
    overrides = {f: getattr(data, f) for f in VISUAL_FIELDS if getattr(data, f) is not None}
    v = _new_version_from_current(db, char, data.change_note or "Cập nhật ngoại hình", **overrides)
    activity.record(db, "character", f"Nhân vật '{char.name}' → phiên bản v{v.version_no}",
                    channel_id=link.channel_id, details={"character_id": char.id, "version_id": v.id})
    db.commit()
    return get_link(db, link.channel_id, char.id)


def list_versions(db: Session, link: ChannelCharacter) -> list[VersionOut]:
    char = link.character
    versions = db.scalars(
        select(CharacterVersion)
        .where(CharacterVersion.character_id == char.id)
        .order_by(CharacterVersion.version_no.desc())
    ).all()
    return [version_out(v, char.current_version_id) for v in versions]


def activate_version(db: Session, link: ChannelCharacter, version_id: int) -> ChannelCharacter:
    char = require_owner(link)
    v = db.scalar(select(CharacterVersion).where(
        CharacterVersion.id == version_id, CharacterVersion.character_id == char.id))
    if v is None:
        raise NotFound("Phiên bản không thuộc nhân vật này")
    char.current_version_id = v.id
    activity.record(db, "character", f"Nhân vật '{char.name}' dùng lại phiên bản v{v.version_no}",
                    channel_id=link.channel_id, details={"character_id": char.id, "version_id": v.id})
    db.commit()
    return get_link(db, link.channel_id, char.id)


def upload_image(
    db: Session, link: ChannelCharacter, slot: str, data: bytes, expression_name: str | None, note: str
) -> ChannelCharacter:
    char = require_owner(link)
    if slot not in IMAGE_SLOTS:
        raise AppError(f"slot phải là một trong {IMAGE_SLOTS}")
    cur = char.current_version
    info = storage.save_image(data, Path("channels") / str(char.channel_id) / "characters" / str(char.id))
    path = info["path"]
    if slot == "avatar":
        overrides, label = {"avatar_image": path}, "ảnh đại diện"
    elif slot == "full_body":
        overrides, label = {"full_body_image": path}, "ảnh toàn thân"
    elif slot == "reference":
        refs = list(cur.reference_images) if cur else []
        if path in refs:
            raise AppError("Ảnh tham chiếu này đã có trong thư viện")
        if len(refs) >= MAX_REFERENCE_IMAGES:
            raise AppError(f"Tối đa {MAX_REFERENCE_IMAGES} ảnh tham chiếu")
        overrides, label = {"reference_images": refs + [path]}, "ảnh tham chiếu"
    else:
        name = (expression_name or "").strip().lower()
        if not name or len(name) > 40:
            raise AppError("Cần tên biểu cảm (1–40 ký tự), VD: happy, sleepy")
        exprs = [e for e in (cur.expressions if cur else []) if e["name"] != name]
        overrides, label = {"expressions": exprs + [{"name": name, "image": path}]}, f"biểu cảm '{name}'"
    v = _new_version_from_current(db, char, note or f"Cập nhật {label}", **overrides)
    activity.record(db, "character", f"Nhân vật '{char.name}': {label} → v{v.version_no}",
                    channel_id=link.channel_id, details={"character_id": char.id, "version_id": v.id})
    db.commit()
    return get_link(db, link.channel_id, char.id)


def remove_image(db: Session, link: ChannelCharacter, slot: str, key: str) -> ChannelCharacter:
    """Remove a reference image (key=path) or an expression (key=name) → new version."""
    char = require_owner(link)
    cur = char.current_version
    if cur is None:
        raise AppError("Nhân vật chưa có phiên bản")
    if slot == "reference":
        if key not in cur.reference_images:
            raise NotFound("Không có ảnh tham chiếu này trong phiên bản hiện tại")
        overrides = {"reference_images": [p for p in cur.reference_images if p != key]}
    elif slot == "expression":
        if not any(e["name"] == key for e in cur.expressions):
            raise NotFound("Không có biểu cảm này")
        overrides = {"expressions": [e for e in cur.expressions if e["name"] != key]}
    elif slot in ("avatar", "full_body"):
        overrides = {"avatar_image" if slot == "avatar" else "full_body_image": None}
    else:
        raise AppError("slot không hợp lệ")
    v = _new_version_from_current(db, char, f"Gỡ {slot} '{key}'", **overrides)
    activity.record(db, "character", f"Nhân vật '{char.name}': gỡ {slot} → v{v.version_no}",
                    channel_id=link.channel_id, details={"character_id": char.id})
    db.commit()
    return get_link(db, link.channel_id, char.id)


def set_role(db: Session, link: ChannelCharacter, role: CharacterRole) -> ChannelCharacter:
    """Role is per channel; a channel may set role even for a granted character."""
    _set_role(db, link.channel_id, link, role)
    activity.record(db, "character", f"Đặt '{link.character.name}' là nhân vật "
                    f"{'chính' if role == CharacterRole.PRIMARY else 'phụ'}", channel_id=link.channel_id)
    db.commit()
    return get_link(db, link.channel_id, link.character_id)


def delete_character(db: Session, link: ChannelCharacter) -> None:
    char = require_owner(link)
    name, cid = char.name, link.channel_id
    try:
        db.delete(char)
        activity.record(db, "character", f"Xóa nhân vật '{name}'", channel_id=cid)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("Nhân vật đang được dùng trong nội dung video, không thể xóa. "
                       "Hãy lưu trữ (archive) thay vì xóa.") from exc


def grant(db: Session, link: ChannelCharacter, data: GrantCreate) -> ChannelCharacter:
    char = require_owner(link)
    if data.target_channel_id == link.channel_id:
        raise AppError("Không thể cấp quyền cho chính kênh sở hữu")
    target = db.get(Channel, data.target_channel_id)
    if target is None:
        raise NotFound("Không tìm thấy kênh nhận quyền")
    if db.scalar(select(ChannelCharacter.id).where(
            ChannelCharacter.channel_id == target.id, ChannelCharacter.character_id == char.id)):
        raise Conflict(f"Kênh '{target.name}' đã có quyền dùng nhân vật này")
    g = ChannelCharacter(channel_id=target.id, character_id=char.id, is_owner=False,
                         role=CharacterRole.SECONDARY, note=data.note)
    db.add(g)
    db.flush()
    _set_role(db, target.id, g, data.role)
    activity.record(db, "character", f"Cấp quyền dùng '{char.name}' cho kênh '{target.name}'",
                    channel_id=link.channel_id, details={"character_id": char.id, "target": target.id})
    activity.record(db, "character", f"Được cấp quyền dùng nhân vật '{char.name}'", channel_id=target.id)
    db.commit()
    return get_link(db, link.channel_id, char.id)


def revoke(db: Session, link: ChannelCharacter, target_channel_id: int) -> ChannelCharacter:
    char = require_owner(link)
    g = db.scalar(select(ChannelCharacter).where(
        ChannelCharacter.channel_id == target_channel_id,
        ChannelCharacter.character_id == char.id,
        ChannelCharacter.is_owner.is_(False),
    ))
    if g is None:
        raise NotFound("Kênh này chưa được cấp quyền")
    try:
        db.delete(g)
        activity.record(db, "character", f"Thu hồi quyền dùng '{char.name}' của kênh #{target_channel_id}",
                        channel_id=link.channel_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("Kênh kia đang dùng nhân vật trong nội dung, không thể thu hồi") from exc
    return get_link(db, link.channel_id, char.id)
