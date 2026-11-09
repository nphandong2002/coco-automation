"""Content, assets, rendering and video models (used from Phase 2).

Channel isolation is enforced in the database with COMPOSITE foreign keys:
a child row carries `channel_id` and references (channel_id, parent_id) of its
parent, so a row can never point at another channel's project/video/character.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, str_enum
from app.models.enums import (
    AssetKind,
    ContentType,
    IdeaStatus,
    JobStatus,
    LicenseType,
    PrivacyStatus,
    ProductionStatus,
)


class ContentIdea(TimestampMixin, Base):
    __tablename__ = "content_ideas"
    __table_args__ = (
        # fingerprint = normalized hash of (type, theme, setting, audio) to block duplicates
        UniqueConstraint("channel_id", "fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content_type: Mapped[ContentType] = mapped_column(str_enum(ContentType, "content_type"), nullable=False)
    theme: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    attributes: Mapped[dict] = mapped_column(default=dict, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[IdeaStatus] = mapped_column(
        str_enum(IdeaStatus, "idea_status"), default=IdeaStatus.NEW, nullable=False
    )


class VideoTemplate(TimestampMixin, Base):
    __tablename__ = "video_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NULL = shared template available to every channel
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    content_type: Mapped[ContentType] = mapped_column(str_enum(ContentType, "content_type"), nullable=False)
    config: Mapped[dict] = mapped_column(default=dict, nullable=False)


class Asset(TimestampMixin, Base):
    """Image/audio/video file with mandatory licence information."""

    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("channel_id", "sha256"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NULL = shared asset library
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[AssetKind] = mapped_column(str_enum(AssetKind, "asset_kind"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_sec: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    license_type: Mapped[LicenseType] = mapped_column(str_enum(LicenseType, "license_type"), nullable=False)
    license_source: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    attribution: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    tags: Mapped[list] = mapped_column(default=list, nullable=False)


class ContentProject(TimestampMixin, Base):
    __tablename__ = "content_projects"
    __table_args__ = (
        UniqueConstraint("channel_id", "id", name="uq_content_projects_channel_id_id"),
        # character must be OWNED by or GRANTED to this channel
        ForeignKeyConstraint(
            ["channel_id", "character_id"],
            ["channel_characters.channel_id", "channel_characters.character_id"],
            name="fk_content_projects_channel_character",
        ),
        # pinned version must belong to that character
        ForeignKeyConstraint(
            ["character_id", "character_version_id"],
            ["character_versions.character_id", "character_versions.id"],
            name="fk_content_projects_character_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    idea_id: Mapped[int | None] = mapped_column(ForeignKey("content_ideas.id", ondelete="SET NULL"))
    template_id: Mapped[int | None] = mapped_column(ForeignKey("video_templates.id", ondelete="SET NULL"))
    character_id: Mapped[int | None] = mapped_column(Integer)
    character_version_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content_type: Mapped[ContentType] = mapped_column(str_enum(ContentType, "content_type"), nullable=False)
    theme: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    script: Mapped[str] = mapped_column(Text, default="", nullable=False)
    setting: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    background_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    animation: Mapped[dict] = mapped_column(default=dict, nullable=False)
    # [{"asset_id": 1, "volume": 0.8, "loop": true}]
    audio_layers: Mapped[list] = mapped_column(default=list, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    # {"focus": 25, "short_break": 5, "long_break": 15, "cycles_before_long": 4}
    pomodoro: Mapped[dict | None] = mapped_column()
    youtube_title: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    youtube_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    youtube_tags: Mapped[list] = mapped_column(default=list, nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[ProductionStatus] = mapped_column(
        str_enum(ProductionStatus, "production_status"), default=ProductionStatus.DRAFT, nullable=False
    )


class VideoJob(TimestampMixin, Base):
    """Render queue entry. Worker takes ONE heavy job at a time (8 GB RAM host)."""

    __tablename__ = "video_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["channel_id", "content_project_id"],
            ["content_projects.channel_id", "content_projects.id"],
            name="fk_video_jobs_project",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        str_enum(JobStatus, "job_status"), default=JobStatus.QUEUED, nullable=False, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(100))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    render_config: Mapped[dict] = mapped_column(default=dict, nullable=False)
    output_path: Mapped[str | None] = mapped_column(String(512))
    log_path: Mapped[str | None] = mapped_column(String(512))
    error: Mapped[str | None] = mapped_column(Text)


class Video(TimestampMixin, Base):
    __tablename__ = "videos"
    __table_args__ = (
        UniqueConstraint("channel_id", "id", name="uq_videos_channel_id_id"),
        ForeignKeyConstraint(
            ["channel_id", "content_project_id"],
            ["content_projects.channel_id", "content_projects.id"],
            name="fk_videos_project",
            ondelete="SET NULL",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_project_id: Mapped[int | None] = mapped_column(Integer)
    video_job_id: Mapped[int | None] = mapped_column(ForeignKey("video_jobs.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    fps: Mapped[float] = mapped_column(Float, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    thumbnail_path: Mapped[str | None] = mapped_column(String(512))
    qc_report: Mapped[dict] = mapped_column(default=dict, nullable=False)
    youtube_video_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    privacy_status: Mapped[PrivacyStatus | None] = mapped_column(str_enum(PrivacyStatus, "privacy_status"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublishingJob(TimestampMixin, Base):
    __tablename__ = "publishing_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["channel_id", "video_id"],
            ["videos.channel_id", "videos.id"],
            name="fk_publishing_jobs_video",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        str_enum(JobStatus, "job_status"), default=JobStatus.QUEUED, nullable=False, index=True
    )
    # Default PRIVATE: review on YouTube before going public
    privacy_status: Mapped[PrivacyStatus] = mapped_column(
        str_enum(PrivacyStatus, "privacy_status"), default=PrivacyStatus.PRIVATE, nullable=False
    )
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tags: Mapped[list] = mapped_column(default=list, nullable=False)
    playlist_id: Mapped[str | None] = mapped_column(String(64))
    category_id: Mapped[str] = mapped_column(String(8), default="10", nullable=False)
    upload_session_uri: Mapped[str | None] = mapped_column(Text)  # resumable upload
    bytes_uploaded: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    youtube_video_id: Mapped[str | None] = mapped_column(String(32))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    history: Mapped[list] = mapped_column(default=list, nullable=False)
