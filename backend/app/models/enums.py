"""Enumerations shared by models and API schemas."""
from __future__ import annotations

import enum


class ChannelStatus(str, enum.Enum):
    """Effective channel status (computed, see Channel.status)."""

    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class CharacterRole(str, enum.Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


class ContentType(str, enum.Enum):
    STUDY_WITH_ME = "study_with_me"
    POMODORO = "pomodoro"
    COZY_AMBIENCE = "cozy_ambience"
    RAIN_SOUNDS = "rain_sounds"
    FIREPLACE_SOUNDS = "fireplace_sounds"
    SLEEP_AMBIENCE = "sleep_ambience"
    READING_ROOM = "reading_room"
    CAFE_AMBIENCE = "cafe_ambience"
    NATURE_AMBIENCE = "nature_ambience"


class IdeaStatus(str, enum.Enum):
    NEW = "new"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    USED = "used"


class ProductionStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    QUEUED = "queued"
    RENDERING = "rendering"
    RENDERED = "rendered"
    FAILED = "failed"
    PUBLISHED = "published"


class AssetKind(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FONT = "font"
    MODEL = "model"            # .glb 3D character / prop


class AssetSource(str, enum.Enum):
    UPLOAD = "upload"          # file provided by the user (licence declared by the user)
    GENERATED = "generated"    # created by Coco Automation's procedural generators (owned)


class VideoJobType(str, enum.Enum):
    FULL = "full"              # final video -> creates a `videos` row
    PREVIEW = "preview"        # short test render, output kept only as a job artefact


class WorkerState(str, enum.Enum):
    IDLE = "idle"
    RENDERING = "rendering"
    UPLOADING = "uploading"
    SYNCING = "syncing"
    WAITING_LOCK = "waiting_lock"
    STOPPED = "stopped"


# Allowed final video durations (minutes) — see project requirements §7
DURATION_CHOICES: tuple[int, ...] = (30, 60, 120, 240, 360, 480)
PREVIEW_SECONDS_RANGE: tuple[int, int] = (10, 300)


class LicenseType(str, enum.Enum):
    OWNED = "owned"
    CC0 = "cc0"
    CC_BY = "cc_by"
    ROYALTY_FREE = "royalty_free"
    LICENSED = "licensed"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PrivacyStatus(str, enum.Enum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"


class CredentialStatus(str, enum.Enum):
    VALID = "valid"
    EXPIRED = "expired"
    REVOKED = "revoked"


class DataSource(str, enum.Enum):
    """Where a metric value came from. Dashboards must show this distinction."""

    YOUTUBE_API = "youtube_api"
    ESTIMATED = "estimated"


class SyncStatus(str, enum.Enum):
    """Outcome of the last analytics sync of a channel."""

    OK = "ok"                  # everything synced
    PARTIAL = "partial"        # channel data synced, some videos failed
    ERROR = "error"            # nothing could be synced (see error_kind)


class LogLevel(str, enum.Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
