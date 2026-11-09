"""All ORM models. Importing this package registers every table on Base.metadata."""
from app.models.base import Base
from app.models.channel import Channel, YoutubeCredential
from app.models.character import ChannelCharacter, Character, CharacterVersion
from app.models.ops import AnalyticsDaily, AnalyticsVideo, SchedulerJob, SystemLog, WorkerStatus
from app.models.production import (
    Asset,
    ContentIdea,
    ContentProject,
    PublishingJob,
    Video,
    VideoJob,
    VideoTemplate,
)

__all__ = [
    "Base",
    "Channel",
    "YoutubeCredential",
    "Character",
    "CharacterVersion",
    "ChannelCharacter",
    "ContentIdea",
    "ContentProject",
    "VideoTemplate",
    "Asset",
    "VideoJob",
    "Video",
    "PublishingJob",
    "AnalyticsDaily",
    "AnalyticsVideo",
    "SchedulerJob",
    "SystemLog",
    "WorkerStatus",
]
