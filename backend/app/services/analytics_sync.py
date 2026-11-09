"""Pulls REAL metrics from YouTube (Analytics API + Data API) into the analytics tables.

Rules
  * Only YouTube-reported numbers are stored (data_source='youtube_api'). Days YouTube returns
    nothing for are simply absent — never filled with zeros or estimates.
  * Per-channel isolation: every channel is synced with its own OAuth token; a failure (revoked
    token, quota, missing scope) is recorded in `analytics_sync_state` of THAT channel only.
  * Idempotent + restart safe: rows are upserted, each video is committed separately, and
    the next sync re-reads the last `analytics_overlap_days` days because YouTube revises them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.integrations.youtube import analytics as yta
from app.integrations.youtube.client import AUTH, PERMANENT, QUOTA, RETRYABLE, ApiError, YouTubeClient
from app.models import (
    AnalyticsChannelSnapshot,
    AnalyticsDaily,
    AnalyticsRetention,
    AnalyticsSyncState,
    AnalyticsVideo,
    Channel,
    SchedulerJob,
    Video,
    YoutubeCredential,
)
from app.models.enums import CredentialStatus, DataSource, JobStatus, LogLevel, SyncStatus
from app.services import activity, youtube_service

log = logging.getLogger("coco.analytics")

JOB_TYPE = "analytics_sync"
MAX_CONSECUTIVE_VIDEO_FAILURES = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_today() -> date:
    return _now().date()


@dataclass
class SyncResult:
    channel_id: int
    status: str                      # ok | partial | error | skipped
    days_written: int = 0
    videos_synced: int = 0
    videos_failed: int = 0
    retention_synced: int = 0
    error_kind: str | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- value parsing
def _f(row: dict, key: str) -> float | None:
    v = row.get(key)
    return None if v is None else float(v)


def _i(row: dict, key: str) -> int:
    v = row.get(key)
    return 0 if v is None else int(round(float(v)))


def _day(row: dict) -> date:
    return date.fromisoformat(str(row["day"])[:10])


def daily_row(channel_id: int, row: dict, synced_at: datetime) -> dict:
    return dict(
        channel_id=channel_id, day=_day(row), views=_i(row, "views"),
        watch_time_minutes=_f(row, "estimatedMinutesWatched") or 0.0,
        average_view_duration_sec=_f(row, "averageViewDuration"),
        average_view_percentage=_f(row, "averageViewPercentage"),
        subscribers_gained=_i(row, "subscribersGained"), subscribers_lost=_i(row, "subscribersLost"),
        likes=_i(row, "likes"), comments=_i(row, "comments"),
        data_source=DataSource.YOUTUBE_API, synced_at=synced_at,
    )


def video_row(channel_id: int, video_id: int, row: dict, synced_at: datetime) -> dict:
    return dict(
        channel_id=channel_id, video_id=video_id, day=_day(row), views=_i(row, "views"),
        watch_time_minutes=_f(row, "estimatedMinutesWatched") or 0.0,
        average_view_duration_sec=_f(row, "averageViewDuration"),
        average_view_percentage=_f(row, "averageViewPercentage"),
        subscribers_gained=_i(row, "subscribersGained"), likes=_i(row, "likes"), comments=_i(row, "comments"),
        data_source=DataSource.YOUTUBE_API, synced_at=synced_at,
    )


def _upsert(db: Session, model, rows: list[dict], conflict: list[str]) -> None:  # noqa: ANN001
    if not rows:
        return
    for i in range(0, len(rows), 500):
        stmt = pg_insert(model).values(rows[i:i + 500])
        update = {c.name: stmt.excluded[c.name] for c in model.__table__.columns
                  if c.name not in conflict and c.name != "id"}
        db.execute(stmt.on_conflict_do_update(index_elements=conflict, set_=update))


# ---------------------------------------------------------------- state
def get_state(db: Session, channel_id: int) -> AnalyticsSyncState | None:
    return db.get(AnalyticsSyncState, channel_id)


def _save_state(channel_id: int, result: SyncResult, synced_through: date | None, retry_after: datetime | None) -> None:
    now = _now()
    with SessionLocal() as db:
        st = db.get(AnalyticsSyncState, channel_id)
        was_error = st is not None and st.status == SyncStatus.ERROR
        if st is None:
            st = AnalyticsSyncState(channel_id=channel_id, status=SyncStatus(result.status))
            db.add(st)
        st.status = SyncStatus(result.status)
        st.last_attempt_at = now
        st.days_written = result.days_written
        st.videos_synced = result.videos_synced
        st.videos_failed = result.videos_failed
        st.error_kind = result.error_kind
        st.last_error = (result.error or None) and result.error[:1000]
        st.retry_after = retry_after
        if result.status in ("ok", "partial"):
            st.last_success_at = now
            if synced_through is not None:
                st.synced_through = max(synced_through, st.synced_through or synced_through)
        if result.status == "error":
            activity.record(db, "analytics", f"Đồng bộ Analytics thất bại: {(result.error or '')[:300]}",
                            channel_id=channel_id, level=LogLevel.WARNING,
                            details={"kind": result.error_kind})
        elif was_error:
            activity.record(db, "analytics", "Đồng bộ Analytics đã hoạt động trở lại", channel_id=channel_id)
        db.commit()


# ---------------------------------------------------------------- main entry
def sync_channel(channel_id: int, *, http: httpx.Client | None = None, backfill_days: int | None = None,
                 today: date | None = None, client: YouTubeClient | None = None,
                 heartbeat=None) -> SyncResult:  # noqa: ANN001
    """Sync one channel. Never raises for API problems — they are recorded in the sync state."""
    s = get_settings()
    today = today or _utc_today()
    with SessionLocal() as db:
        ch = db.get(Channel, channel_id)
        if ch is None:
            return SyncResult(channel_id, "skipped", error="Kênh không tồn tại")
        cred = db.scalar(select(YoutubeCredential).where(YoutubeCredential.channel_id == channel_id))
        if not ch.enabled:
            return SyncResult(channel_id, "skipped", notes=["Kênh đang tạm dừng"])
        if cred is None or cred.status != CredentialStatus.VALID:
            return SyncResult(channel_id, "skipped", notes=["Kênh chưa kết nối YouTube"])
        scopes = list(cred.scopes or [])
        st = db.get(AnalyticsSyncState, channel_id)
        synced_through = st.synced_through if st else None

    if yta.ANALYTICS_SCOPE not in scopes:
        res = SyncResult(channel_id, "error", error_kind="scope",
                         error="Kênh được kết nối trước khi có quyền Analytics. Hãy ngắt kết nối và kết nối lại "
                               "YouTube để cấp quyền xem báo cáo (yt-analytics.readonly).")
        _save_state(channel_id, res, None, None)
        return res

    lookback = min(backfill_days, s.analytics_max_backfill_days) if backfill_days else s.analytics_initial_days
    first_start = today - timedelta(days=lookback)
    if backfill_days or synced_through is None:
        start = first_start
    else:
        start = max(first_start, synced_through - timedelta(days=s.analytics_overlap_days))
    end = today

    owns_client = client is None
    client = client or youtube_service.client_for(channel_id, http)
    result = SyncResult(channel_id, "ok")
    new_through: date | None = None
    retry_after: datetime | None = None
    try:
        new_through = _sync_channel_level(client, channel_id, start, end, today, result)
        _sync_videos(client, channel_id, start, first_start, end, today, result, heartbeat)
        _sync_retention(client, channel_id, today, result, heartbeat)
    except ApiError as exc:
        _fail(result, exc)
        if exc.kind == QUOTA:
            from app.worker.publisher import next_quota_reset
            retry_after = next_quota_reset()
        if result.days_written == 0 and new_through is None and result.videos_synced == 0:
            result.status = "error"
        else:
            result.status = "partial"
    except Exception as exc:  # noqa: BLE001 - one channel must never break the worker
        log.exception("Analytics sync of channel %s crashed", channel_id)
        result.error_kind, result.error = "internal", f"{exc.__class__.__name__}: {exc}"
        result.status = "error" if result.days_written == 0 else "partial"
    finally:
        if owns_client:
            client.close()
    if result.status == "ok" and result.videos_failed:
        result.status = "partial"
    _save_state(channel_id, result, new_through, retry_after)
    log.info("Analytics sync channel=%s status=%s days=%s videos=%s failed=%s",
             channel_id, result.status, result.days_written, result.videos_synced, result.videos_failed)
    return result


def _fail(result: SyncResult, exc: ApiError) -> None:
    kind = {AUTH: "auth", QUOTA: "quota", RETRYABLE: "network"}.get(exc.kind)
    if yta.is_scope_error(exc):
        kind = "scope"
        result.error = ("YouTube từ chối truy cập báo cáo Analytics (403). Kiểm tra đã bật 'YouTube Analytics API' "
                        "trong Google Cloud và kết nối lại kênh để cấp quyền yt-analytics.readonly. "
                        f"Chi tiết: {exc}")
    else:
        result.error = str(exc)
    result.error_kind = kind or "api"


# ---------------------------------------------------------------- stage 1: channel level
def _sync_channel_level(client: YouTubeClient, channel_id: int, start: date, end: date, today: date,
                        result: SyncResult) -> date | None:
    rows = yta.channel_daily(client, start, end)
    now = _now()
    values = [daily_row(channel_id, r, now) for r in rows]
    new_through = max((v["day"] for v in values), default=None)
    with SessionLocal() as db:
        _upsert(db, AnalyticsDaily, values, ["channel_id", "day"])
        db.commit()
    result.days_written = len(values)

    info = client.my_channel()  # Data API: subscriber count is not part of the daily report
    stats = info.get("statistics") or {}
    hidden = bool(stats.get("hiddenSubscriberCount"))
    snap = dict(
        channel_id=channel_id, day=today,
        subscribers=None if hidden or "subscriberCount" not in stats else int(stats["subscriberCount"]),
        subscribers_hidden=hidden, total_views=int(stats.get("viewCount") or 0),
        video_count=int(stats.get("videoCount") or 0),
        data_source=DataSource.YOUTUBE_API, synced_at=now,
    )
    with SessionLocal() as db:
        _upsert(db, AnalyticsChannelSnapshot, [snap], ["channel_id", "day"])
        db.commit()
    return new_through


# ---------------------------------------------------------------- stage 2: per video
def _sync_videos(client: YouTubeClient, channel_id: int, start: date, first_start: date, end: date,
                 today: date, result: SyncResult, heartbeat=None) -> None:  # noqa: ANN001
    s = get_settings()
    now = _now()
    with SessionLocal() as db:
        vids = db.execute(
            select(Video.id, Video.youtube_video_id, Video.published_at)
            .where(Video.channel_id == channel_id, Video.youtube_video_id.is_not(None))
        ).all()
        last = dict(db.execute(
            select(AnalyticsVideo.video_id, func.max(AnalyticsVideo.synced_at))
            .where(AnalyticsVideo.channel_id == channel_id).group_by(AnalyticsVideo.video_id)
        ).all())
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    vids = sorted(vids, key=lambda v: last.get(v.id) or epoch)[: s.analytics_max_videos_per_sync]
    consecutive = 0
    for vid, yt_id, published_at in vids:
        if heartbeat:
            heartbeat()
        if published_at is not None and published_at > now:
            continue  # scheduled in the future: YouTube has no report yet
        vstart = start if vid in last else first_start
        if published_at is not None:
            vstart = max(vstart, published_at.date())
        if vstart > end:
            continue
        try:
            rows = yta.video_daily(client, yt_id, vstart, end)
        except ApiError as exc:
            if exc.kind in (AUTH, QUOTA) or yta.is_scope_error(exc):
                raise
            result.videos_failed += 1
            result.notes.append(f"video {yt_id}: {exc}")
            consecutive += 1
            if consecutive >= MAX_CONSECUTIVE_VIDEO_FAILURES:
                raise
            continue
        consecutive = 0
        values = [video_row(channel_id, vid, r, now) for r in rows]
        with SessionLocal() as db:
            _upsert(db, AnalyticsVideo, values, ["video_id", "day"])
            db.commit()
        result.videos_synced += 1


# ---------------------------------------------------------------- stage 3: retention
def _sync_retention(client: YouTubeClient, channel_id: int, today: date, result: SyncResult,
                    heartbeat=None) -> None:  # noqa: ANN001
    s = get_settings()
    now = _now()
    min_published = now - timedelta(days=s.analytics_retention_min_age_days)
    stale = now - timedelta(hours=s.analytics_retention_refresh_hours)
    with SessionLocal() as db:
        cand = db.execute(
            select(Video.id, Video.youtube_video_id, Video.published_at)
            .outerjoin(AnalyticsRetention, AnalyticsRetention.video_id == Video.id)
            .where(Video.channel_id == channel_id, Video.youtube_video_id.is_not(None),
                   Video.published_at.is_not(None), Video.published_at <= min_published,
                   or_(AnalyticsRetention.id.is_(None), AnalyticsRetention.synced_at < stale))
            .order_by(AnalyticsRetention.synced_at.nulls_first(), Video.published_at.desc())
            .limit(s.analytics_max_retention_per_sync)
        ).all()
    for vid, yt_id, published_at in cand:
        if heartbeat:
            heartbeat()
        try:
            points = yta.video_retention(client, yt_id, published_at.date(), today)
        except ApiError as exc:
            if exc.kind in (AUTH, QUOTA) or yta.is_scope_error(exc):
                raise
            result.notes.append(f"retention {yt_id}: {exc}")
            continue
        if not points:
            continue  # not enough views for YouTube to return a curve — store nothing
        row = dict(channel_id=channel_id, video_id=vid, points=points,
                   data_source=DataSource.YOUTUBE_API, synced_at=now)
        with SessionLocal() as db:
            _upsert(db, AnalyticsRetention, [row], ["video_id"])
            db.commit()
        result.retention_synced += 1


# ---------------------------------------------------------------- queue (scheduler_jobs)
def enqueue_sync(db: Session, channel_id: int, backfill_days: int | None = None) -> tuple[SchedulerJob, bool]:
    """Queue a sync. At most one active job per channel (dedupe_key is released when the job ends)."""
    key = f"{JOB_TYPE}:{channel_id}"
    existing = db.scalar(select(SchedulerJob).where(SchedulerJob.dedupe_key == key))
    if existing is not None:
        return existing, False
    job = SchedulerJob(channel_id=channel_id, job_type=JOB_TYPE, dedupe_key=key,
                       payload={"backfill_days": backfill_days} if backfill_days else {},
                       status=JobStatus.QUEUED, run_at=_now(), max_attempts=1, timeout_sec=1800)
    db.add(job)
    db.commit()
    return job, True


def claim_job(worker_id: str) -> tuple[int, int, dict] | None:
    now = _now()
    with SessionLocal() as db:
        job = db.scalar(
            select(SchedulerJob)
            .where(SchedulerJob.job_type == JOB_TYPE, SchedulerJob.status == JobStatus.QUEUED,
                   SchedulerJob.run_at <= now)
            .order_by(SchedulerJob.run_at, SchedulerJob.id)
            .with_for_update(skip_locked=True).limit(1)
        )
        if job is None:
            return None
        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.locked_by, job.locked_at = worker_id, now
        db.commit()
        return job.id, int(job.channel_id), dict(job.payload or {})


def finish_job(job_id: int, ok: bool, error: str | None = None) -> None:
    with SessionLocal() as db:
        job = db.get(SchedulerJob, job_id)
        if job is None:
            return
        job.status = JobStatus.SUCCEEDED if ok else JobStatus.FAILED
        job.finished_at = _now()
        job.last_error = (error or None) and error[:1000]
        job.dedupe_key = None  # release: a new sync may be queued now
        job.locked_by = None
        db.commit()


def recover_running_jobs() -> int:
    """Called by the lock holder at start-up: RUNNING jobs belong to a dead worker -> queue them again."""
    with SessionLocal() as db:
        jobs = db.scalars(select(SchedulerJob).where(SchedulerJob.job_type == JOB_TYPE,
                                                     SchedulerJob.status == JobStatus.RUNNING)).all()
        for j in jobs:
            j.status = JobStatus.QUEUED
            j.locked_by = None
        db.commit()
        return len(jobs)


def enqueue_due_channels(db: Session, now: datetime | None = None) -> int:
    """Automatic schedule: queue channels whose last attempt is older than the sync interval."""
    s = get_settings()
    now = now or _now()
    interval = timedelta(minutes=s.analytics_sync_interval_minutes)
    rows = db.execute(
        select(Channel.id, YoutubeCredential.updated_at, AnalyticsSyncState)
        .join(YoutubeCredential, YoutubeCredential.channel_id == Channel.id)
        .outerjoin(AnalyticsSyncState, AnalyticsSyncState.channel_id == Channel.id)
        .where(Channel.enabled.is_(True), YoutubeCredential.status == CredentialStatus.VALID)
    ).all()
    n = 0
    for channel_id, cred_updated, st in rows:
        if st is not None:
            if st.retry_after is not None and st.retry_after > now:
                continue
            if st.last_attempt_at is not None and now - st.last_attempt_at < interval:
                continue
            # scope/auth problems are permanent until the user reconnects the channel
            if st.error_kind in ("scope", "auth") and st.last_attempt_at is not None \
                    and cred_updated <= st.last_attempt_at:
                continue
        _, created = enqueue_sync(db, channel_id)
        n += int(created)
    return n
