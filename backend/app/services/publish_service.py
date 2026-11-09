"""Publishing Manager: create/list/cancel/retry publishing jobs and compute schedule slots."""
from __future__ import annotations

import re
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import storage
from app.models import Channel, ContentProject, PublishingJob, Video
from app.models.enums import JobStatus, LogLevel, PrivacyStatus
from app.schemas.publishing import PublishCreate, PublishJobOut
from app.services import activity
from app.services.errors import AppError, Conflict, NotFound

ACTIVE = (JobStatus.QUEUED, JobStatus.RUNNING)
MIN_LEAD = timedelta(minutes=5)          # YouTube needs publishAt in the future
SLOT_LOOKAHEAD_DAYS = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def add_history(job: PublishingJob, event: str, detail: str = "") -> None:
    # JSON column: assign a NEW list so SQLAlchemy sees the change
    job.history = [*(job.history or []), {"at": _now().isoformat(timespec="seconds"), "event": event,
                                          "detail": detail[:500]}][-100:]


def has_event(job: PublishingJob, event: str) -> bool:
    return any(h.get("event") == event for h in (job.history or []))


# ---------------------------------------------------------------- metadata
_TAG_BAD = re.compile(r"[<>]")


def clean_tags(tags: list[str]) -> list[str]:
    """YouTube: tags total <= 500 chars (quoted tags count +2), no angle brackets."""
    out: list[str] = []
    total = 0
    for t in tags:
        t = _TAG_BAD.sub("", str(t)).strip()
        if not t or t.lower() in {x.lower() for x in out}:
            continue
        cost = len(t) + (2 if " " in t else 0) + 1
        if total + cost > 500:
            break
        out.append(t)
        total += cost
    return out


def validate_title(title: str) -> str:
    title = title.strip()
    if not title:
        raise AppError("Tiêu đề YouTube không được để trống", 422)
    if len(title) > 100:
        raise AppError("Tiêu đề YouTube tối đa 100 ký tự", 422)
    if _TAG_BAD.search(title):
        raise AppError("Tiêu đề YouTube không được chứa < hoặc >", 422)
    return title


# ---------------------------------------------------------------- schedule slots
def _tz(ch: Channel) -> ZoneInfo:
    name = (ch.publish_schedule or {}).get("timezone") or "UTC"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _taken(db: Session, channel_id: int) -> set[datetime]:
    rows = db.scalars(select(PublishingJob.publish_at).where(
        PublishingJob.channel_id == channel_id, PublishingJob.publish_at.is_not(None),
        PublishingJob.status.in_((JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.SUCCEEDED)))).all()
    return {r.astimezone(timezone.utc).replace(second=0, microsecond=0) for r in rows}


def next_slots(db: Session, ch: Channel, count: int = 1, after: datetime | None = None) -> list[datetime]:
    """Next free publish times from the channel's weekly schedule (UTC). Empty if no slots configured."""
    slots = (ch.publish_schedule or {}).get("slots") or []
    if not slots:
        return []
    tz = _tz(ch)
    start = max(after or _now(), _now() + MIN_LEAD)
    taken = _taken(db, ch.id)
    by_day: dict[int, list[dtime]] = {}
    for s in slots:
        try:
            hh, mm = str(s["time"]).split(":")
            by_day.setdefault(int(s["weekday"]), []).append(dtime(int(hh), int(mm)))
        except (KeyError, ValueError):
            continue
    out: list[datetime] = []
    day0 = start.astimezone(tz).date()
    for d in range(SLOT_LOOKAHEAD_DAYS):
        day = day0 + timedelta(days=d)
        for t in sorted(by_day.get(day.weekday(), [])):
            cand = datetime.combine(day, t, tzinfo=tz).astimezone(timezone.utc)
            if cand >= start and cand not in taken:
                out.append(cand)
                if len(out) >= count:
                    return out
    return out


# ---------------------------------------------------------------- create
def create_job(db: Session, channel: Channel, data: PublishCreate) -> PublishingJob:
    video = db.get(Video, data.video_id)
    if video is None or video.channel_id != channel.id:
        raise NotFound(f"Không tìm thấy video #{data.video_id} trong kênh này")
    if video.youtube_video_id:
        raise Conflict(f"Video này đã được đăng lên YouTube ({video.youtube_video_id})")
    if not channel.enabled:
        raise AppError("Kênh đang tạm dừng", 409)
    if not channel.youtube_connected:
        raise AppError("Kênh chưa kết nối YouTube (hoặc cần kết nối lại)", 409)
    if not (video.qc_report or {}).get("passed"):
        raise AppError("Video chưa qua kiểm tra chất lượng sau render, không thể đăng", 409)
    try:
        if not storage.resolve(video.file_path).is_file():
            raise AppError("File video không còn trên đĩa", 409)
    except storage.StorageError as exc:
        raise AppError(str(exc), 409) from exc
    busy = db.scalar(select(func.count()).select_from(PublishingJob).where(
        PublishingJob.video_id == video.id, PublishingJob.status.in_(ACTIVE)))
    if busy:
        raise Conflict("Video này đã có tác vụ đăng đang chờ/đang chạy")

    project = db.get(ContentProject, video.content_project_id) if video.content_project_id else None
    title = validate_title(data.title or (project.youtube_title if project and project.youtube_title else video.title))
    description = data.description if data.description is not None else (project.youtube_description if project else "")
    tags = clean_tags(data.tags if data.tags is not None else (project.youtube_tags if project else []))

    publish_at = data.publish_at
    if data.use_next_slot:
        slots = next_slots(db, channel, 1)
        if not slots:
            raise AppError("Kênh chưa có lịch đăng (hoặc đã hết slot trống 60 ngày). Hãy cấu hình lịch đăng của kênh.", 409)
        publish_at = slots[0]
    privacy = data.privacy
    if publish_at is not None:
        if publish_at.tzinfo is None:
            raise AppError("publish_at phải có múi giờ", 422)
        if publish_at < _now() + MIN_LEAD:
            raise AppError("Thời gian công khai phải ở tương lai (ít nhất 5 phút)", 422)
        privacy = PrivacyStatus.PRIVATE  # YouTube: scheduled videos are private until publishAt

    job = PublishingJob(
        channel_id=channel.id, video_id=video.id, privacy_status=privacy, publish_at=publish_at, title=title,
        description=description or "", tags=tags, playlist_id=data.playlist_id or None,
        category_id=data.category_id, next_attempt_at=data.upload_after, history=[],
    )
    add_history(job, "created", f"privacy={privacy.value}" + (f", publish_at={publish_at.isoformat()}" if publish_at else ""))
    db.add(job)
    activity.record(db, "publishing", f"Xếp lịch đăng video '{title}' ({privacy.value}"
                    f"{', công khai ' + publish_at.strftime('%d/%m %H:%M UTC') if publish_at else ''})",
                    channel_id=channel.id)
    db.commit()
    return job


# ---------------------------------------------------------------- read / modify
def get_job(db: Session, job_id: int) -> PublishingJob:
    job = db.get(PublishingJob, job_id)
    if job is None:
        raise NotFound(f"Không tìm thấy tác vụ đăng #{job_id}")
    return job


def job_out(db: Session, job: PublishingJob) -> PublishJobOut:
    ch = db.get(Channel, job.channel_id)
    video = db.get(Video, job.video_id)
    pct = None
    if video and video.size_bytes:
        pct = round(min(1.0, job.bytes_uploaded / video.size_bytes), 4)
    return PublishJobOut(
        id=job.id, channel_id=job.channel_id, channel_name=ch.name if ch else "?", video_id=job.video_id,
        video_title=video.title if video else None, thumbnail_url=storage.media_url(video.thumbnail_path) if video else None,
        status=job.status.value, privacy_status=job.privacy_status.value, publish_at=job.publish_at, title=job.title,
        description=job.description, tags=job.tags, playlist_id=job.playlist_id, category_id=job.category_id,
        bytes_uploaded=job.bytes_uploaded, size_bytes=video.size_bytes if video else None, progress=pct,
        attempts=job.attempts, max_attempts=job.max_attempts, next_attempt_at=job.next_attempt_at,
        youtube_video_id=job.youtube_video_id,
        youtube_url=f"https://www.youtube.com/watch?v={job.youtube_video_id}" if job.youtube_video_id else None,
        uploaded_at=job.uploaded_at, last_error=job.last_error, history=job.history or [], created_at=job.created_at,
    )


def list_jobs(db: Session, channel_id: int | None = None, status: JobStatus | None = None,
              limit: int = 100) -> list[PublishJobOut]:
    stmt = select(PublishingJob)
    if channel_id is not None:
        stmt = stmt.where(PublishingJob.channel_id == channel_id)
    if status is not None:
        stmt = stmt.where(PublishingJob.status == status)
    rows = db.scalars(stmt.order_by(PublishingJob.created_at.desc(), PublishingJob.id.desc()).limit(min(limit, 500)))
    return [job_out(db, j) for j in rows]


def cancel_job(db: Session, job: PublishingJob) -> PublishingJob:
    if job.status not in ACTIVE:
        raise Conflict("Chỉ hủy được tác vụ đang chờ hoặc đang chạy")
    was_running = job.status == JobStatus.RUNNING
    job.status = JobStatus.CANCELLED  # a running worker notices this on its next progress tick
    job.next_attempt_at = None
    add_history(job, "cancelled", "đang chạy, sẽ dừng upload" if was_running else "")
    activity.record(db, "publishing", f"Đã hủy tác vụ đăng #{job.id}", channel_id=job.channel_id,
                    level=LogLevel.WARNING)
    db.commit()
    return job


def retry_job(db: Session, job: PublishingJob) -> PublishingJob:
    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise Conflict("Chỉ thử lại được tác vụ thất bại hoặc đã hủy")
    if job.youtube_video_id is None:
        busy = db.scalar(select(func.count()).select_from(PublishingJob).where(
            PublishingJob.video_id == job.video_id, PublishingJob.status.in_(ACTIVE)))
        if busy:
            raise Conflict("Video này đã có tác vụ đăng khác đang chờ")
    job.status = JobStatus.QUEUED
    job.attempts = 0
    job.next_attempt_at = None
    job.last_error = None
    add_history(job, "retry", "người dùng thử lại")
    activity.record(db, "publishing", f"Thử lại tác vụ đăng #{job.id}", channel_id=job.channel_id)
    db.commit()
    return job


def queue_status(db: Session) -> dict:
    counts = dict(db.execute(select(PublishingJob.status, func.count()).group_by(PublishingJob.status)).all())
    return {s.value: int(counts.get(s, 0)) for s in JobStatus}
