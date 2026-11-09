"""Analytics API. Read endpoints serve stored YouTube data; sync endpoints queue work for the analytics worker."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import Channel, YoutubeCredential
from app.models.enums import CredentialStatus
from app.services import analytics_service as svc
from app.services import analytics_sync, channel_service
from app.services.errors import AppError

router = APIRouter(tags=["analytics"])


def _scope(channel_id: int | None, start: date | None, end: date | None, topic: str | None,
           video_status: str | None, db: Session, default_days: int = 28) -> svc.Scope:
    if channel_id is not None:
        channel_service.get_channel(db, channel_id)  # 404 for unknown channel
    return svc.make_scope(channel_id, start, end, topic, video_status, default_days)


@router.get("/analytics/summary")
def summary(channel_id: int | None = None, start: date | None = None, end: date | None = None,
            topic: str | None = None, video_status: str | None = None, db: Session = Depends(get_db)):
    return svc.summary(db, _scope(channel_id, start, end, topic, video_status, db))


@router.get("/analytics/timeseries")
def timeseries(channel_id: int | None = None, start: date | None = None, end: date | None = None,
               topic: str | None = None, video_status: str | None = None,
               granularity: str = "day", split: bool = False, db: Session = Depends(get_db)):
    return svc.timeseries(db, _scope(channel_id, start, end, topic, video_status, db), granularity, split)


@router.get("/analytics/distribution")
def distribution(channel_id: int | None = None, start: date | None = None, end: date | None = None,
                 topic: str | None = None, video_status: str | None = None, by: str = "channel",
                 db: Session = Depends(get_db)):
    return svc.distribution(db, _scope(channel_id, start, end, topic, video_status, db), by)


@router.get("/analytics/channels/compare")
def compare(start: date | None = None, end: date | None = None, db: Session = Depends(get_db)):
    return svc.compare_channels(db, svc.make_scope(None, start, end))


@router.get("/analytics/videos")
def videos(channel_id: int | None = None, start: date | None = None, end: date | None = None,
           topic: str | None = None, video_status: str | None = None, sort: str = "score",
           limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    # videos are judged over their whole life by default: use a long window unless the user narrows it
    scope = _scope(channel_id, start, end, topic, video_status, db, default_days=90)
    return svc.videos(db, scope, sort, limit)


@router.get("/analytics/videos/{video_id}/retention")
def video_retention(video_id: int, db: Session = Depends(get_db)):
    return svc.video_retention(db, video_id)


@router.get("/analytics/retention")
def channel_retention(channel_id: int | None = None, db: Session = Depends(get_db)):
    if channel_id is not None:
        channel_service.get_channel(db, channel_id)
    return svc.channel_retention(db, channel_id)


@router.get("/analytics/insights")
def insights(channel_id: int | None = None, start: date | None = None, end: date | None = None,
             topic: str | None = None, video_status: str | None = None, db: Session = Depends(get_db)):
    return svc.insights(db, _scope(channel_id, start, end, topic, video_status, db, default_days=90))


# ---------------------------------------------------------------- sync
@router.get("/analytics/sync")
def sync_status(channel_id: int | None = None, db: Session = Depends(get_db)):
    if channel_id is not None:
        channel_service.get_channel(db, channel_id)
    return svc.sync_status(db, channel_id)


def _queue(db: Session, channel_id: int, backfill_days: int | None) -> dict:
    ch = channel_service.get_channel(db, channel_id)
    cred = db.scalar(select(YoutubeCredential).where(YoutubeCredential.channel_id == ch.id))
    if cred is None or cred.status != CredentialStatus.VALID:
        raise AppError("Kênh chưa kết nối YouTube hoặc cần kết nối lại", 409)
    if not ch.enabled:
        raise AppError("Kênh đang tạm dừng — bật kênh trước khi đồng bộ", 409)
    job, created = analytics_sync.enqueue_sync(db, ch.id, backfill_days)
    return {"channel_id": ch.id, "job_id": job.id, "queued": created,
            "message": "Đã xếp lịch đồng bộ" if created else "Đang có tác vụ đồng bộ chờ/đang chạy cho kênh này"}


@router.post("/channels/{channel_id}/analytics/sync", status_code=202)
def sync_channel(channel_id: int, backfill_days: int | None = Query(None, ge=1), db: Session = Depends(get_db)):
    limit = get_settings().analytics_max_backfill_days
    if backfill_days is not None and backfill_days > limit:
        raise AppError(f"backfill_days tối đa {limit}", 422)
    return _queue(db, channel_id, backfill_days)


@router.post("/analytics/sync", status_code=202)
def sync_all(db: Session = Depends(get_db)):
    """Queue every connected, enabled channel. Channels that cannot sync are reported, not fatal."""
    results = []
    for ch in db.scalars(select(Channel).order_by(Channel.id)).all():
        try:
            results.append(_queue(db, ch.id, None))
        except AppError as exc:
            results.append({"channel_id": ch.id, "queued": False, "message": exc.message})
    return {"results": results, "queued": sum(1 for r in results if r["queued"])}
