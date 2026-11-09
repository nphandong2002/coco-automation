from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, str_enum, utcnow
from app.models.enums import CharacterRole

if TYPE_CHECKING:
    from app.models.channel import Channel


class Character(TimestampMixin, Base):
    """A character OWNED by exactly one channel.

    Visual identity lives in immutable `CharacterVersion` rows. Any change to
    appearance creates a new version, so videos pinned to a version always render
    the same look (consistency requirement).
    """

    __tablename__ = "characters"
    __table_args__ = (UniqueConstraint("channel_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    species: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "character_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_characters_current_version_id_character_versions",
        )
    )
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    owner_channel: Mapped[Channel] = relationship(back_populates="owned_characters")
    versions: Mapped[list[CharacterVersion]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="CharacterVersion.character_id",
        order_by="CharacterVersion.version_no",
    )
    current_version: Mapped[CharacterVersion | None] = relationship(
        foreign_keys=[current_version_id], post_update=True
    )
    links: Mapped[list[ChannelCharacter]] = relationship(
        back_populates="character", cascade="all, delete-orphan", passive_deletes=True
    )


class CharacterVersion(Base):
    """Immutable snapshot of a character's visual identity."""

    __tablename__ = "character_versions"
    __table_args__ = (
        UniqueConstraint("character_id", "version_no"),
        # target for composite FKs (character_id, version_id) from content_projects
        UniqueConstraint("character_id", "id", name="uq_character_versions_character_id_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    appearance: Mapped[str] = mapped_column(Text, default="", nullable=False)
    art_style: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    primary_colors: Mapped[list] = mapped_column(default=list, nullable=False)
    outfit: Mapped[str] = mapped_column(Text, default="", nullable=False)
    personality: Mapped[str] = mapped_column(Text, default="", nullable=False)
    usual_settings: Mapped[list] = mapped_column(default=list, nullable=False)
    allowed_animations: Mapped[list] = mapped_column(default=list, nullable=False)
    # [{"name": "happy", "image": "channels/1/characters/3/<sha>.png"}]
    expressions: Mapped[list] = mapped_column(default=list, nullable=False)
    avatar_image: Mapped[str | None] = mapped_column(String(512))
    full_body_image: Mapped[str | None] = mapped_column(String(512))
    reference_images: Mapped[list] = mapped_column(default=list, nullable=False)
    change_note: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    character: Mapped[Character] = relationship(
        back_populates="versions", foreign_keys=[character_id]
    )


class ChannelCharacter(Base):
    """Which channels may USE a character, and in what role.

    The owner channel always has a row (is_owner=True). Another channel can only use
    the character when the owner explicitly grants it (is_owner=False row).
    At most one PRIMARY character per channel (partial unique index).
    """

    __tablename__ = "channel_characters"
    __table_args__ = (
        UniqueConstraint("channel_id", "character_id"),
        Index(
            "uq_channel_characters_one_primary",
            "channel_id",
            unique=True,
            postgresql_where=text("role = 'primary'"),
            sqlite_where=text("role = 'primary'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[CharacterRole] = mapped_column(
        str_enum(CharacterRole, "character_role"), default=CharacterRole.SECONDARY, nullable=False
    )
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)

    channel: Mapped[Channel] = relationship(back_populates="character_links")
    character: Mapped[Character] = relationship(back_populates="links")
