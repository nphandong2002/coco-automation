from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import EncryptedJSON
from app.models.base import Base, TimestampMixin, str_enum
from app.models.enums import ChannelStatus, CredentialStatus

if TYPE_CHECKING:
    from app.models.character import ChannelCharacter, Character


class Channel(TimestampMixin, Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    target_country: Mapped[str] = mapped_column(String(8), default="US", nullable=False)
    topics: Mapped[list] = mapped_column(default=list, nullable=False)
    # {"theme": "...", "palette": [...], "mood": "...", "keywords": [...]}
    visual_style: Mapped[dict] = mapped_column(default=dict, nullable=False)
    # {"ambience": [...], "music": "...", "notes": "..."}
    audio_style: Mapped[dict] = mapped_column(default=dict, nullable=False)
    # {"timezone": "Asia/Bangkok", "slots": [{"weekday": 0..6, "time": "HH:MM"}]}
    publish_schedule: Mapped[dict] = mapped_column(default=dict, nullable=False)
    avatar_path: Mapped[str | None] = mapped_column(String(512))
    banner_path: Mapped[str | None] = mapped_column(String(512))

    # User-controlled on/off switch
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Set by the system when an operation for this channel fails; cleared on success
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cloned_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL")
    )

    credential: Mapped[YoutubeCredential | None] = relationship(
        back_populates="channel", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )
    owned_characters: Mapped[list[Character]] = relationship(
        back_populates="owner_channel", cascade="all, delete-orphan", passive_deletes=True
    )
    character_links: Mapped[list[ChannelCharacter]] = relationship(
        back_populates="channel", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def youtube_connected(self) -> bool:
        return self.credential is not None and self.credential.status == CredentialStatus.VALID

    @property
    def status(self) -> ChannelStatus:
        """Effective status. Priority: Paused > Error > Disconnected > Active."""
        if not self.enabled:
            return ChannelStatus.PAUSED
        if self.last_error:
            return ChannelStatus.ERROR
        if not self.youtube_connected:
            return ChannelStatus.DISCONNECTED
        return ChannelStatus.ACTIVE


class YoutubeCredential(TimestampMixin, Base):
    """OAuth credential of ONE channel. Token payload is Fernet-encrypted."""

    __tablename__ = "youtube_credentials"
    __table_args__ = (UniqueConstraint("channel_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    youtube_channel_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    youtube_channel_title: Mapped[str | None] = mapped_column(String(200))
    google_account_email: Mapped[str | None] = mapped_column(String(200))
    scopes: Mapped[list] = mapped_column(default=list, nullable=False)
    token_encrypted: Mapped[dict] = mapped_column(EncryptedJSON, nullable=False)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[CredentialStatus] = mapped_column(
        str_enum(CredentialStatus, "credential_status"),
        default=CredentialStatus.VALID,
        nullable=False,
    )
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    channel: Mapped[Channel] = relationship(back_populates="credential")

