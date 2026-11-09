"""Read side of Analytics: KPIs, time series, comparisons, per-video performance, insights.

Provenance rules
  * every number is read from rows written by the YouTube sync (data_source='youtube_api');
  * nothing is generated: no rows -> value None + state 'not_synced' (never a fake 0);
  * Coco-calculated values (scores, growth %, recommendations) carry `source: "calculated"`;
  * the newest `analytics_preliminary_days` days are flagged preliminary (YouTube still revises them).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    AnalyticsChannelSnapshot,
    AnalyticsDaily,
    AnalyticsRetention,
    AnalyticsSyncState,
    AnalyticsVideo,
    Channel,
    ContentProject,
    PublishingJob,
    Video,
    VideoJob,
    WorkerStatus,
    YoutubeCredential,
)
from app.models.enums import (
    DURATION_CHOICES,
    CredentialStatus,
    DataSource,
    JobStatus,
    PrivacyStatus,
    ProductionStatus,
    SyncStatus,
)
from app.services import analytics_scoring as sc
from app.services.errors import AppError

API = DataSource.YOUTUBE_API
MAX_RANGE_DAYS = 800


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- scope
@dataclass
class Scope:
    start: date
    end: date
    channel_id: int | None = None
    topic: str | None = None            # content_type value
    video_status: str | None = None     # private | unlisted | public

    @property
    def video_filtered(self) -> bool:
        return bool(self.topic or self.video_status)

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def previous(self) -> "Scope":
        return Scope(self.start - timedelta(days=self.days), self.start - timedelta(days=1),
                     self.channel_id, self.topic, self.video_status)


def make_scope(channel_id: int | None = None, start: date | None = None, end: date | None = None,
               topic: str | None = None, video_status: str | None = None, default_days: int = 28) -> Scope:
    end = end or _now().date()
    start = start or end - timedelta(days=default_days - 1)
    if start > end:
        raise AppError("Ngày bắt đầu phải trước ngày kết thúc", 422)
    if (end - start).days > MAX_RANGE_DAYS:
        raise AppError(f"Khoảng thời gian tối đa {MAX_RANGE_DAYS} ngày", 422)
    if video_status and video_status not in {p.value for p in PrivacyStatus}:
        raise AppError("video_status phải là private, unlisted hoặc public", 422)
    return Scope(start, end, channel_id, topic or None, video_status or None)


def preliminary_since() -> date:
    return _now().date() - timedelta(days=get_settings().analytics_preliminary_days)


def _pct_change(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / prev * 100, 1)


# ---------------------------------------------------------------- video filters
def _video_filters(scope: Scope) -> list:
    conds = [Video.youtube_video_id.is_not(None)]
    if scope.channel_id is not None:
        conds.append(Video.channel_id == scope.channel_id)
    if scope.video_status:
        conds.append(Video.privacy_status == PrivacyStatus(scope.video_status))
    if scope.topic:
        conds.append(ContentProject.content_type == scope.topic)
    return conds


def _cp_join():
    return (ContentProject.channel_id == Video.channel_id) & (ContentProject.id == Video.content_project_id)


def _wavg(col):  # noqa: ANN001
    """View-weighted average of a per-day average column (ignores days where YouTube gave no value)."""
    weight = case((col.is_not(None), AnalyticsVideo.views), else_=0)
    return func.sum(col * AnalyticsVideo.views) / func.nullif(func.sum(weight), 0)


def _wavg_daily(col):  # noqa: ANN001
    weight = case((col.is_not(None), AnalyticsDaily.views), else_=0)
    return func.sum(col * AnalyticsDaily.views) / func.nullif(func.sum(weight), 0)


# ---------------------------------------------------------------- sync status
def sync_status(db: Session, channel_id: int | None = None) -> dict:
    s = get_settings()
    q = (select(Channel.id, Channel.name, Channel.enabled, YoutubeCredential.status, YoutubeCredential.scopes,
                AnalyticsSyncState)
         .outerjoin(YoutubeCredential, YoutubeCredential.channel_id == Channel.id)
         .outerjoin(AnalyticsSyncState, AnalyticsSyncState.channel_id == Channel.id)
         .order_by(Channel.id))
    if channel_id is not None:
        q = q.where(Channel.id == channel_id)
    now = _now()
    stale_after = timedelta(minutes=s.analytics_sync_interval_minutes * 2 + 30)
    out = []
    for cid, name, enabled, cred_status, scopes, st in db.execute(q).all():
        connected = cred_status == CredentialStatus.VALID
        if not connected:
            state = "disconnected"
        elif st is None or st.last_success_at is None:
            state = "error" if st is not None and st.status == SyncStatus.ERROR else "not_synced"
        elif st.status == SyncStatus.ERROR:
            state = "error"
        elif now - st.last_success_at > stale_after:
            state = "stale"
        else:
            state = "synced"
        out.append({
            "channel_id": cid, "channel_name": name, "enabled": enabled, "connected": connected,
            "state": state,
            "status": st.status.value if st else None,
            "last_attempt_at": st.last_attempt_at if st else None,
            "last_success_at": st.last_success_at if st else None,
            "synced_through": st.synced_through if st else None,
            "videos_synced": st.videos_synced if st else 0, "videos_failed": st.videos_failed if st else 0,
            "error_kind": st.error_kind if st else None, "error": st.last_error if st else None,
            "retry_after": st.retry_after if st else None,
        })
    worker = db.scalars(select(WorkerStatus).where(WorkerStatus.kind == "analytics")
                        .order_by(WorkerStatus.heartbeat_at.desc()).limit(1)).first()
    alive = bool(worker and worker.state.value != "stopped"
                 and (now - worker.heartbeat_at).total_seconds() < s.worker_stale_seconds)
    return {"channels": out, "worker_alive": alive, "interval_minutes": s.analytics_sync_interval_minutes}


# ---------------------------------------------------------------- KPI summary
def _totals(db: Session, scope: Scope) -> dict:
    """Aggregate KPIs of one period. Channel-level table unless video filters force the video table."""
    if scope.video_filtered:
        tbl = AnalyticsVideo
        q = (select(func.count(), func.sum(tbl.views), func.sum(tbl.watch_time_minutes),
                    func.sum(tbl.subscribers_gained), func.sum(tbl.likes), func.sum(tbl.comments),
                    _wavg(tbl.average_view_duration_sec), _wavg(tbl.average_view_percentage),
                    func.max(tbl.synced_at))
             .select_from(AnalyticsVideo)
             .join(Video, (Video.channel_id == AnalyticsVideo.channel_id) & (Video.id == AnalyticsVideo.video_id))
             .outerjoin(ContentProject, _cp_join())
             .where(*_video_filters(scope), AnalyticsVideo.day.between(scope.start, scope.end),
                    AnalyticsVideo.data_source == API))
        lost = None
    else:
        tbl = AnalyticsDaily
        q = (select(func.count(), func.sum(tbl.views), func.sum(tbl.watch_time_minutes),
                    func.sum(tbl.subscribers_gained), func.sum(tbl.likes), func.sum(tbl.comments),
                    _wavg_daily(tbl.average_view_duration_sec), _wavg_daily(tbl.average_view_percentage),
                    func.max(tbl.synced_at), func.sum(tbl.subscribers_lost))
             .where(tbl.day.between(scope.start, scope.end), tbl.data_source == API))
        if scope.channel_id is not None:
            q = q.where(tbl.channel_id == scope.channel_id)
        lost = True
    if scope.video_filtered and scope.channel_id is not None:
        q = q.where(AnalyticsVideo.channel_id == scope.channel_id)
    row = db.execute(q).one()
    n, views, wt, gained, likes, comments, avd, avp, synced = row[:9]
    if not n:
        return {"has_data": False, "synced_at": None}
    t = {
        "has_data": True, "days": n, "synced_at": synced,
        "views": int(views or 0), "watch_time_minutes": float(wt or 0), "subscribers_gained": int(gained or 0),
        "likes": int(likes or 0), "comments": int(comments or 0),
        "average_view_duration_sec": float(avd) if avd is not None else None,
        "average_view_percentage": float(avp) if avp is not None else None,
        "subscribers_lost": int(row[9] or 0) if lost else None,
    }
    t["subscribers_net"] = t["subscribers_gained"] - t["subscribers_lost"] if lost else None
    return t


def _latest_subscribers(db: Session, channel_id: int | None) -> dict:
    latest = (select(AnalyticsChannelSnapshot.channel_id.label("cid"),
                     func.max(AnalyticsChannelSnapshot.day).label("d"))
              .group_by(AnalyticsChannelSnapshot.channel_id).subquery())
    q = (select(AnalyticsChannelSnapshot)
         .join(latest, (latest.c.cid == AnalyticsChannelSnapshot.channel_id) & (latest.c.d == AnalyticsChannelSnapshot.day)))
    if channel_id is not None:
        q = q.where(AnalyticsChannelSnapshot.channel_id == channel_id)
    snaps = db.scalars(q).all()
    total_channels = db.scalar(select(func.count()).select_from(Channel).where(
        *([Channel.id == channel_id] if channel_id is not None else []))) or 0
    counted = [s for s in snaps if s.subscribers is not None]
    return {
        "value": sum(s.subscribers for s in counted) if counted else None,
        "source": "youtube_api" if counted else "not_synced",
        "synced_at": max((s.synced_at for s in counted), default=None),
        "channels_counted": len(counted), "channels_total": total_channels,
        "channels_hidden": sum(1 for s in snaps if s.subscribers_hidden),
    }


def _kpi(cur: dict, prev: dict, key: str) -> dict:
    v = cur.get(key) if cur["has_data"] else None
    p = prev.get(key) if prev["has_data"] else None
    return {"value": v, "previous": p, "change_pct": _pct_change(v, p),
            "source": "youtube_api" if v is not None else "not_synced"}


def _production_counts(db: Session, channel_id: int | None) -> dict:
    def cnt(stmt, col):  # noqa: ANN001
        return int(db.scalar(stmt.where(col == channel_id) if channel_id is not None else stmt) or 0)

    published = cnt(select(func.count()).select_from(Video).where(Video.youtube_video_id.is_not(None)), Video.channel_id)
    rendering = cnt(select(func.count()).select_from(VideoJob).where(
        VideoJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])), VideoJob.channel_id)
    uploading = cnt(select(func.count()).select_from(PublishingJob).where(
        PublishingJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])), PublishingJob.channel_id)
    failed_render = cnt(select(func.count()).select_from(ContentProject).where(
        ContentProject.status == ProductionStatus.FAILED), ContentProject.channel_id)
    failed_pub = cnt(select(func.count()).select_from(PublishingJob).where(
        PublishingJob.status == JobStatus.FAILED), PublishingJob.channel_id)
    return {"videos_published": published, "videos_processing": rendering + uploading,
            "videos_failed": failed_render + failed_pub,
            "detail": {"render_active": rendering, "upload_active": uploading,
                       "render_failed": failed_render, "upload_failed": failed_pub}}


def summary(db: Session, scope: Scope) -> dict:
    cur, prev = _totals(db, scope), _totals(db, scope.previous())
    top = videos(db, scope, sort="views", limit=1)["items"]
    top = [t for t in top if t["has_data"] and t["views"]]
    sync = sync_status(db, scope.channel_id)["channels"]
    best = compare_channels(db, scope)["best"] if scope.channel_id is None else None
    return {
        "range": {"start": scope.start, "end": scope.end, "days": scope.days},
        "filters": {"channel_id": scope.channel_id, "topic": scope.topic, "video_status": scope.video_status},
        "basis": "videos" if scope.video_filtered else "channel",
        "data_state": "synced" if cur["has_data"] else "not_synced",
        "preliminary_since": preliminary_since(),
        "last_synced_at": cur.get("synced_at"),
        "kpis": {k: _kpi(cur, prev, k) for k in (
            "views", "watch_time_minutes", "average_view_duration_sec", "average_view_percentage",
            "subscribers_gained", "subscribers_lost", "subscribers_net", "likes", "comments")},
        "subscribers_total": _latest_subscribers(db, scope.channel_id),
        "production": _production_counts(db, scope.channel_id),
        "top_video": top[0] if top else None,
        "best_channel": best,
        "sync": {"connected": sum(1 for c in sync if c["connected"]),
                 "synced": sum(1 for c in sync if c["state"] in ("synced", "stale")),
                 "not_synced": sum(1 for c in sync if c["state"] == "not_synced"),
                 "errors": [{"channel_id": c["channel_id"], "channel_name": c["channel_name"],
                             "kind": c["error_kind"], "error": c["error"]} for c in sync if c["state"] == "error"]},
    }


# ---------------------------------------------------------------- time series
def _bucket(day: date, granularity: str) -> date:
    if granularity == "week":
        return day - timedelta(days=day.weekday())
    if granularity == "month":
        return day.replace(day=1)
    return day


def timeseries(db: Session, scope: Scope, granularity: str = "day", split: bool = False) -> dict:
    if granularity not in ("day", "week", "month"):
        raise AppError("granularity phải là day, week hoặc month", 422)
    if scope.video_filtered:
        t = AnalyticsVideo
        q = (select(t.channel_id, t.day, t.views, t.watch_time_minutes, t.subscribers_gained,
                    cast(0, Float).label("lost"), t.likes, t.comments)
             .join(Video, (Video.channel_id == t.channel_id) & (Video.id == t.video_id))
             .outerjoin(ContentProject, _cp_join())
             .where(*_video_filters(scope), t.day.between(scope.start, scope.end), t.data_source == API))
    else:
        t = AnalyticsDaily
        q = (select(t.channel_id, t.day, t.views, t.watch_time_minutes, t.subscribers_gained,
                    t.subscribers_lost, t.likes, t.comments)
             .where(t.day.between(scope.start, scope.end), t.data_source == API))
        if scope.channel_id is not None:
            q = q.where(t.channel_id == scope.channel_id)
    names = dict(db.execute(select(Channel.id, Channel.name)).all())
    prelim = preliminary_since()
    total: dict[date, dict] = {}
    per: dict[int, dict[date, dict]] = defaultdict(dict)

    def add(bucket_map: dict, key: date, r) -> None:  # noqa: ANN001
        b = bucket_map.setdefault(key, {"period": key, "views": 0, "watch_time_minutes": 0.0, "subscribers_net": 0,
                                        "likes": 0, "comments": 0, "preliminary": False})
        b["views"] += int(r.views or 0)
        b["watch_time_minutes"] += float(r.watch_time_minutes or 0)
        b["subscribers_net"] += int(r.subscribers_gained or 0) - int(r[5] or 0)
        b["likes"] += int(r.likes or 0)
        b["comments"] += int(r.comments or 0)
        b["preliminary"] = b["preliminary"] or r.day >= prelim

    for r in db.execute(q).all():
        key = _bucket(r.day, granularity)
        add(total, key, r)
        if split:
            add(per[r.channel_id], key, r)
    sort = lambda m: [m[k] for k in sorted(m)]  # noqa: E731
    return {
        "basis": "videos" if scope.video_filtered else "channel", "granularity": granularity,
        "data_state": "synced" if total else "not_synced", "preliminary_since": prelim,
        "points": sort(total),
        "by_channel": [{"channel_id": cid, "channel_name": names.get(cid, str(cid)), "points": sort(m)}
                       for cid, m in sorted(per.items())] if split else [],
    }


# ---------------------------------------------------------------- distribution (donut)
def distribution(db: Session, scope: Scope, by: str = "channel") -> dict:
    if by == "channel":
        names = dict(db.execute(select(Channel.id, Channel.name)).all())
        if scope.video_filtered:
            t = AnalyticsVideo
            q = (select(t.channel_id, func.sum(t.views)).select_from(t)
                 .join(Video, (Video.channel_id == t.channel_id) & (Video.id == t.video_id))
                 .outerjoin(ContentProject, _cp_join())
                 .where(*_video_filters(scope), t.day.between(scope.start, scope.end), t.data_source == API)
                 .group_by(t.channel_id))
        else:
            t = AnalyticsDaily
            q = (select(t.channel_id, func.sum(t.views)).where(t.day.between(scope.start, scope.end), t.data_source == API)
                 .group_by(t.channel_id))
            if scope.channel_id is not None:
                q = q.where(t.channel_id == scope.channel_id)
        items = [{"key": str(cid), "label": names.get(cid, str(cid)), "views": int(v or 0)} for cid, v in db.execute(q).all()]
    elif by == "topic":
        t = AnalyticsVideo
        q = (select(ContentProject.content_type, func.sum(t.views)).select_from(t)
             .join(Video, (Video.channel_id == t.channel_id) & (Video.id == t.video_id))
             .outerjoin(ContentProject, _cp_join())
             .where(*_video_filters(scope), t.day.between(scope.start, scope.end), t.data_source == API)
             .group_by(ContentProject.content_type))
        items = [{"key": c.value if c else "unknown", "label": c.value if c else "không rõ", "views": int(v or 0)}
                 for c, v in db.execute(q).all()]
    else:
        raise AppError("by phải là channel hoặc topic", 422)
    total = sum(i["views"] for i in items)
    for i in items:
        i["share"] = round(i["views"] / total * 100, 1) if total else None
    items.sort(key=lambda i: i["views"], reverse=True)
    return {"by": by, "total_views": total if items else None,
            "data_state": "synced" if items else "not_synced", "items": items}


# ---------------------------------------------------------------- per-video performance
def videos(db: Session, scope: Scope, sort: str = "score", limit: int = 100) -> dict:
    t = AnalyticsVideo
    in_range = (t.video_id == Video.id) & (t.day.between(scope.start, scope.end)) & (t.data_source == API)
    q = (select(
            Video.id, Video.channel_id, Channel.name, Video.title, Video.youtube_video_id, Video.published_at,
            Video.created_at, Video.duration_sec, Video.privacy_status, ContentProject.content_type,
            ContentProject.theme,
            func.count(t.id), func.sum(t.views), func.sum(t.watch_time_minutes), _wavg(t.average_view_duration_sec),
            _wavg(t.average_view_percentage), func.sum(t.subscribers_gained), func.sum(t.likes), func.sum(t.comments),
            func.min(t.day), func.max(t.synced_at))
         .select_from(Video)
         .join(Channel, Channel.id == Video.channel_id)
         .outerjoin(ContentProject, _cp_join())
         .outerjoin(t, in_range)
         .where(*_video_filters(scope))
         .group_by(Video.id, Channel.name, ContentProject.content_type, ContentProject.theme))
    rows = db.execute(q).all()
    curves = _retention_map(db, [r[0] for r in rows])
    today = _now().date()
    items: list[dict] = []
    for (vid, cid, cname, title, yt_id, published_at, created_at, dur, privacy, ctype, theme,
         n, views, wt, avd, avp, subs, likes, comments, first_day, synced) in rows:
        pub_day = published_at.date() if published_at else None
        exposure_start = max(scope.start, pub_day) if pub_day else scope.start
        exposure_end = min(scope.end, today)
        exposure = max((exposure_end - exposure_start).days + 1, 0)
        curve = curves.get(vid)
        summ = sc.retention_summary(curve) if curve else None
        items.append({
            "video_id": vid, "channel_id": cid, "channel_name": cname, "title": title, "youtube_video_id": yt_id,
            "published_at": published_at, "privacy_status": privacy.value if privacy else None,
            "duration_minutes": round(dur / 60, 1) if dur else None,
            "content_type": ctype.value if ctype else None, "theme": theme or "",
            "has_data": bool(n), "data_state": "synced" if n else "not_synced", "synced_at": synced,
            "views": int(views or 0) if n else None,
            "watch_time_minutes": float(wt or 0) if n else None,
            "average_view_duration_sec": float(avd) if avd is not None else None,
            "average_view_percentage": float(avp) if avp is not None else None,
            "avg_view_pct": float(avp) if avp is not None else None,
            "subscribers_gained": int(subs or 0) if n else None,
            "likes": int(likes or 0) if n else None, "comments": int(comments or 0) if n else None,
            "subs": int(subs or 0), "retention_avg": summ["average"] if summ else None,
            "retention": summ, "has_retention": curve is not None,
            "exposure_days": exposure, "first_data_day": first_day,
        })
    for it in items:   # scoring needs numeric fields
        if not it["has_data"]:
            it.update(views=0, watch_time_minutes=0.0, likes=0, comments=0)
    sc.score_videos(items)
    for it in items:
        if not it["has_data"]:
            it.update(views=None, watch_time_minutes=None, likes=None, comments=None)
        it["engagement_rate"] = it["metrics"]["engagement"]
        it["views_per_day"] = it["metrics"]["views_per_day"]
        it["source"] = "youtube_api"
        it["score_source"] = "calculated"
    keyf = {
        "score": lambda i: (i["score"] is not None, i["score"] or 0),
        "views": lambda i: i["views"] or 0, "watch_time": lambda i: i["watch_time_minutes"] or 0,
        "published": lambda i: i["published_at"] or datetime.min.replace(tzinfo=timezone.utc),
        "retention": lambda i: i["retention_avg"] or 0,
    }.get(sort)
    if keyf is None:
        raise AppError("sort phải là score, views, watch_time, published hoặc retention", 422)
    items.sort(key=keyf, reverse=True)
    return {"items": items[: max(1, min(limit, 500))], "total": len(items),
            "scoring": {"weights": sc.WEIGHTS, "min_days_live": sc.MIN_DAYS_LIVE, "min_cohort": sc.MIN_COHORT,
                        "note": "Điểm do Coco tính từ số liệu YouTube; so sánh trong cùng kênh."}}


def _retention_map(db: Session, video_ids: list[int]) -> dict[int, list[list[float]]]:
    if not video_ids:
        return {}
    return {vid: pts for vid, pts in db.execute(
        select(AnalyticsRetention.video_id, AnalyticsRetention.points)
        .where(AnalyticsRetention.video_id.in_(video_ids), AnalyticsRetention.data_source == API)).all() if pts}


def video_retention(db: Session, video_id: int) -> dict:
    v = db.get(Video, video_id)
    if v is None:
        raise AppError("Video không tồn tại", 404)
    row = db.scalar(select(AnalyticsRetention).where(AnalyticsRetention.video_id == video_id))
    if row is None or not row.points:
        return {"video_id": video_id, "title": v.title, "data_state": "not_synced", "points": [],
                "summary": sc.retention_summary([]), "synced_at": None,
                "note": "YouTube chưa trả đường giữ chân (video quá mới/ít lượt xem) hoặc chưa đồng bộ."}
    return {"video_id": video_id, "title": v.title, "data_state": "synced", "points": row.points,
            "summary": sc.retention_summary(row.points), "synced_at": row.synced_at, "source": "youtube_api"}


def channel_retention(db: Session, channel_id: int | None) -> dict:
    q = select(AnalyticsRetention.points, AnalyticsRetention.synced_at).where(AnalyticsRetention.data_source == API)
    if channel_id is not None:
        q = q.where(AnalyticsRetention.channel_id == channel_id)
    rows = [(p, s) for p, s in db.execute(q).all() if p]
    if not rows:
        return {"data_state": "not_synced", "n_videos": 0, "points": [], "summary": sc.retention_summary([])}
    pts = sc.average_curves([p for p, _ in rows])
    summ = sc.retention_summary(pts)
    return {"data_state": "synced", "n_videos": len(rows), "points": pts, "summary": summ,
            "at_10": summ["at_10"], "synced_at": max(s for _, s in rows)}


# ---------------------------------------------------------------- channel comparison
def compare_channels(db: Session, scope: Scope) -> dict:
    """Per-channel table. Channel-level metrics only (topic/status filters do not apply here)."""
    base = Scope(scope.start, scope.end)
    prev = base.previous()

    def agg(s: Scope) -> dict[int, dict]:
        t = AnalyticsDaily
        q = (select(t.channel_id, func.sum(t.views), func.sum(t.watch_time_minutes), func.sum(t.subscribers_gained),
                    func.sum(t.subscribers_lost), func.sum(t.likes), func.sum(t.comments),
                    _wavg_daily(t.average_view_percentage), func.count(), func.max(t.synced_at))
             .where(t.day.between(s.start, s.end), t.data_source == API).group_by(t.channel_id))
        return {r[0]: r for r in db.execute(q).all()}

    cur, old = agg(base), agg(prev)
    published = dict(db.execute(
        select(Video.channel_id, func.count()).where(
            Video.published_at.is_not(None),
            func.date(Video.published_at).between(scope.start, scope.end)).group_by(Video.channel_id)).all())
    snaps = _snapshot_growth(db, scope)
    sync = {c["channel_id"]: c for c in sync_status(db)["channels"]}
    rows = []
    for cid, name, enabled in db.execute(select(Channel.id, Channel.name, Channel.enabled).order_by(Channel.id)).all():
        r, o = cur.get(cid), old.get(cid)
        views = int(r[1] or 0) if r else None
        wt = float(r[2] or 0) if r else None
        gained, lost = (int(r[3] or 0), int(r[4] or 0)) if r else (None, None)
        interactions = (int(r[5] or 0) + int(r[6] or 0)) if r else None
        rows.append({
            "channel_id": cid, "channel_name": name, "enabled": enabled,
            "data_state": sync.get(cid, {}).get("state", "not_synced") if r is None else "synced",
            "views": views, "watch_time_minutes": wt,
            "subscribers_gained": gained, "subscribers_lost": lost,
            "subscribers_net": None if gained is None else gained - lost,
            "engagement_rate": (interactions / views) if views else None,
            "average_view_percentage": float(r[7]) if r and r[7] is not None else None,
            "videos_published": int(published.get(cid, 0)),
            "views_growth_pct": _pct_change(views, int(o[1] or 0) if o else None),
            "watch_time_growth_pct": _pct_change(wt, float(o[2] or 0) if o else None),
            "subscribers_total": snaps.get(cid, {}).get("latest"),
            "subscribers_growth_pct": snaps.get(cid, {}).get("growth_pct"),
            "source": "youtube_api" if r else "not_synced",
        })
    with_data = [r for r in rows if r["views"] is not None]
    best = max(with_data, key=lambda r: (r["watch_time_minutes"] or 0, r["views"] or 0), default=None)
    return {"range": {"start": scope.start, "end": scope.end},
            "previous_range": {"start": prev.start, "end": prev.end},
            "best": ({"channel_id": best["channel_id"], "channel_name": best["channel_name"],
                      "basis": "watch_time_minutes", "watch_time_minutes": best["watch_time_minutes"],
                      "views": best["views"]} if best else None),
            "growth_note": "Tăng trưởng = % thay đổi so với kỳ liền trước cùng độ dài (Coco tính từ số liệu YouTube).",
            "items": rows}


def _snapshot_growth(db: Session, scope: Scope) -> dict[int, dict]:
    """Subscriber growth from Data API snapshots: needs two snapshots inside the range."""
    t = AnalyticsChannelSnapshot
    rows = db.scalars(select(t).where(t.day.between(scope.start, scope.end), t.subscribers.is_not(None))
                      .order_by(t.channel_id, t.day)).all()
    by: dict[int, list] = defaultdict(list)
    for r in rows:
        by[r.channel_id].append(r)
    latest = {r.channel_id: r.subscribers for r in db.scalars(
        select(t).where(t.subscribers.is_not(None)).order_by(t.channel_id, t.day)).all()}
    out = {}
    for cid, lst in by.items():
        first, last = lst[0], lst[-1]
        growth = _pct_change(last.subscribers, first.subscribers) if last.day != first.day else None
        out[cid] = {"latest": latest.get(cid), "growth_pct": growth}
    for cid, v in latest.items():
        out.setdefault(cid, {"latest": v, "growth_pct": None})
    return out


# ---------------------------------------------------------------- insights
def _group_stats(items: list[dict], keyf, labelf, group: str) -> list[dict]:  # noqa: ANN001
    groups: dict = defaultdict(list)
    for it in items:
        k = keyf(it)
        if k is not None and it["has_data"]:
            groups[k].append(it)
    out = []
    for k, lst in groups.items():
        scored = [i["score"] for i in lst if i["score"] is not None]
        views = sum(i["views"] or 0 for i in lst)
        subs = sum(i["subs"] for i in lst)
        pcts = [i["avg_view_pct"] for i in lst if i["avg_view_pct"] is not None]
        vpd = [i["views_per_day"] for i in lst if i["views_per_day"] is not None]
        out.append({
            "group": group, "key": k, "label": labelf(k), "n_videos": len(lst), "n_scored": len(scored),
            "total_views": views, "avg_views_per_day": round(sum(vpd) / len(vpd), 2) if vpd else None,
            "avg_view_pct": round(sum(pcts) / len(pcts), 1) if pcts else None,
            "subs_per_1k_views": round(subs / views * 1000, 2) if views else None,
            "avg_score": round(sum(scored) / len(scored), 1) if scored else None,
        })
    out.sort(key=lambda g: (g["avg_score"] is not None, g["avg_score"] or 0, g["total_views"]), reverse=True)
    return out


def _first7(db: Session, vids: list[dict]) -> dict[int, dict]:
    """Views/watch time in the first 7 days after publication (only when that window is fully measured)."""
    cand = {v["video_id"]: v["published_at"] for v in vids if v["published_at"]
            and v["published_at"] + timedelta(days=8) <= _now()}
    if not cand:
        return {}
    t = AnalyticsVideo
    rows = db.execute(select(t.video_id, t.day, t.views, t.watch_time_minutes)
                      .where(t.video_id.in_(list(cand)), t.data_source == API)).all()
    acc: dict[int, dict] = {}
    for vid, day, views, wt in rows:
        pub = cand[vid].date()
        a = acc.setdefault(vid, {"views": 0, "wt": 0.0, "first": day})
        a["first"] = min(a["first"], day)
        if pub <= day <= pub + timedelta(days=6):
            a["views"] += int(views or 0)
            a["wt"] += float(wt or 0)
    # require data to start right at publication (otherwise early days are missing, not zero)
    return {vid: a for vid, a in acc.items() if a["first"] <= cand[vid].date() + timedelta(days=2)}


def posting_times(db: Session, vids: list[dict]) -> dict:
    tz_by_channel = {cid: (sched or {}).get("timezone") or "UTC" for cid, sched in
                     db.execute(select(Channel.id, Channel.publish_schedule)).all()}
    f7 = _first7(db, vids)
    hours = {h: [] for h in range(24)}
    days = {d: [] for d in range(7)}
    for v in vids:
        m = f7.get(v["video_id"])
        if m is None:
            continue
        try:
            local = v["published_at"].astimezone(ZoneInfo(tz_by_channel.get(v["channel_id"], "UTC")))
        except Exception:  # noqa: BLE001 - unknown tz name
            local = v["published_at"]
        hours[local.hour].append(m)
        days[local.weekday()].append(m)

    def summarise(buckets: dict, field: str) -> list[dict]:
        return [{field: k, "n": len(lst),
                 "avg_views_7d": round(sum(x["views"] for x in lst) / len(lst), 1) if lst else None,
                 "avg_watch_minutes_7d": round(sum(x["wt"] for x in lst) / len(lst), 1) if lst else None,
                 "reliable": len(lst) >= sc.MIN_SLOT_SAMPLES} for k, lst in sorted(buckets.items())]

    return {"measured_videos": len(f7), "by_hour": summarise(hours, "hour"), "by_weekday": summarise(days, "weekday"),
            "note": "Giờ theo múi giờ của kênh; đo bằng lượt xem 7 ngày đầu sau khi video công khai/đến giờ hẹn. "
                    "Chỉ dùng video đã đủ 8 ngày và có dữ liệu từ lúc đăng."}


def insights(db: Session, scope: Scope) -> dict:
    vids = videos(db, scope, sort="score", limit=500)["items"]
    topics = _group_stats(vids, lambda i: i["content_type"], lambda k: k, "content_type")
    themes = [g for g in _group_stats(vids, lambda i: (i["theme"] or "").strip().lower() or None,
                                      lambda k: k, "theme") if g["n_videos"] >= 1][:10]

    def bucket(i: dict) -> int | None:
        return min(DURATION_CHOICES, key=lambda c: abs(c - i["duration_minutes"])) if i["duration_minutes"] else None

    durations = _group_stats(vids, bucket, lambda k: f"{k} phút", "duration")
    for d in durations:
        d["minutes"] = d["key"]
    durations.sort(key=lambda d: d["minutes"])
    posting = posting_times(db, vids)
    ret = channel_retention(db, scope.channel_id)
    ret_ctx = {"at_10": ret["summary"]["at_10"], "n_videos": ret["n_videos"]} if ret["n_videos"] else None
    weak = [v for v in vids if v["label"] == "weak"]
    scored = sum(1 for v in vids if v["score"] is not None)
    last_upload = db.scalar(select(func.max(PublishingJob.uploaded_at)).where(
        *([PublishingJob.channel_id == scope.channel_id] if scope.channel_id is not None else []),
        PublishingJob.uploaded_at.is_not(None)))
    days_since = (_now() - last_upload).days if last_upload else None
    recs = sc.build_recommendations(topics=topics, durations=durations, posting=posting, retention=ret_ctx,
                                    weak_videos=weak, scored_videos=scored, days_since_upload=days_since)
    return {
        "range": {"start": scope.start, "end": scope.end}, "source": "calculated",
        "videos_total": len(vids), "videos_scored": scored,
        "topics": topics, "themes": themes, "durations": durations, "posting_times": posting,
        "underperformers": [{"video_id": v["video_id"], "title": v["title"], "channel_id": v["channel_id"],
                             "channel_name": v["channel_name"], "score": v["score"], "reasons": v["weak_reasons"]}
                            for v in weak],
        "retention": {"n_videos": ret["n_videos"], "summary": ret["summary"]},
        "recommendations": recs,
    }
