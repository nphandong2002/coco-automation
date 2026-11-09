"""Phase 4: YouTube Analytics sync, KPIs, comparisons, scoring, insights.

YouTube is simulated with httpx.MockTransport. The simulation returns deterministic numbers, so every
assertion checks a value that went through the real sync -> database -> aggregation path.
"""
import time
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import (
    AnalyticsChannelSnapshot,
    AnalyticsDaily,
    AnalyticsRetention,
    AnalyticsSyncState,
    AnalyticsVideo,
    Channel,
    ContentProject,
    SchedulerJob,
    Video,
    YoutubeCredential,
)
from app.models.enums import ContentType, CredentialStatus, DataSource, JobStatus, PrivacyStatus
from app.services import analytics_scoring as sc
from app.services import analytics_service as svc
from app.services import analytics_sync
from app.worker.analytics import AnalyticsWorker
from test_youtube import connect_channel  # noqa: F401  (helper only; fixtures are not imported)

TODAY = datetime.now(timezone.utc).date()


# ============================================================ fake YouTube
class FakeAnalytics:
    """Google token endpoint + Data API channel stats + Analytics reports."""

    def __init__(self):
        self.video_views_per_day: dict[str, int] = {}      # yt id -> views/day
        self.video_errors: dict[str, tuple[int, str]] = {}  # yt id -> (status, reason)
        self.report_error: tuple[int, str] | None = None
        self.no_retention: set[str] = set()
        self.calls: list[dict] = []
        self.subscribers = 1234
        self.hidden = False
        self.revision = 0   # bump to simulate YouTube revising numbers

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://oauth2.googleapis.com/token"):
            return httpx.Response(200, json={"access_token": "ya29.fresh", "expires_in": 3600})
        if "/youtube/v3/channels" in url:
            stats = {"viewCount": "99999", "videoCount": "7", "hiddenSubscriberCount": self.hidden}
            if not self.hidden:
                stats["subscriberCount"] = str(self.subscribers)
            return httpx.Response(200, json={"items": [{"id": "UC1", "snippet": {"title": "T"}, "statistics": stats}]})
        if url.startswith("https://youtubeanalytics.googleapis.com/v2/reports"):
            return self._report(dict(request.url.params))
        return httpx.Response(404, json={"error": {"message": "unexpected " + url}})

    @staticmethod
    def _err(status: int, reason: str) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": reason, "errors": [{"reason": reason}]}})

    def _report(self, p: dict) -> httpx.Response:
        self.calls.append(p)
        if self.report_error:
            return self._err(*self.report_error)
        start, end = date.fromisoformat(p["startDate"]), date.fromisoformat(p["endDate"])
        flt = p.get("filters", "")
        yt = flt.split("==")[1] if flt else None
        if yt in self.video_errors:
            return self._err(*self.video_errors[yt])
        if p["dimensions"] == "elapsedVideoTimeRatio":
            if yt in self.no_retention:
                return httpx.Response(200, json={"columnHeaders": [], "rows": []})
            rows = [[round(i / 100, 2), max(0.2, 1 - i / 130)] for i in range(1, 101)]
            return httpx.Response(200, json={"columnHeaders": [{"name": "elapsedVideoTimeRatio"},
                                                               {"name": "audienceWatchRatio"}], "rows": rows})
        assert p["dimensions"] == "day"
        names = [m for m in p["metrics"].split(",")]
        rows = []
        d = start
        while d <= min(end, TODAY - timedelta(days=1)):   # YouTube has no data for today yet
            vpd = self.video_views_per_day.get(yt, 0) if yt else sum(self.video_views_per_day.values())
            vpd += self.revision
            values = {"views": vpd, "estimatedMinutesWatched": vpd * 4.5, "averageViewDuration": 270.0,
                      "averageViewPercentage": 42.5, "subscribersGained": vpd // 50, "subscribersLost": vpd // 200,
                      "likes": vpd // 10, "comments": vpd // 40}
            rows.append([d.isoformat()] + [values[n] for n in names])
            d += timedelta(days=1)
        return httpx.Response(200, json={"columnHeaders": [{"name": "day"}] + [{"name": n} for n in names],
                                         "rows": rows})


@pytest.fixture
def yt():
    return FakeAnalytics()


@pytest.fixture
def http(yt):
    c = httpx.Client(transport=httpx.MockTransport(yt))
    yield c
    c.close()


def add_video(db, channel_id, yt_id, days_ago=20, minutes=60, privacy=PrivacyStatus.PUBLIC,
              content_type=None, theme="", title=None):
    project_id = None
    if content_type:
        p = ContentProject(channel_id=channel_id, title=title or yt_id, content_type=content_type, theme=theme,
                           fingerprint=f"fp-{channel_id}-{yt_id}")
        db.add(p)
        db.flush()
        project_id = p.id
    v = Video(channel_id=channel_id, content_project_id=project_id, title=title or f"Video {yt_id}",
              file_path=f"x/{yt_id}.mp4", duration_sec=minutes * 60, width=1920, height=1080, fps=30,
              size_bytes=10, youtube_video_id=yt_id, privacy_status=privacy,
              published_at=datetime.now(timezone.utc) - timedelta(days=days_ago))
    db.add(v)
    db.commit()
    return v.id


@pytest.fixture
def ch1(channel):
    ch = channel("cozy", "Cozy Study")
    with SessionLocal() as db:
        connect_channel(db, ch["id"])
    return ch


def sync(channel_id, http, **kw):
    return analytics_sync.sync_channel(channel_id, http=http, **kw)


# ============================================================ pure logic
def test_percentile_ranks_handles_ties_and_none():
    assert sc.percentile_ranks([1, 2, 3]) == [0.0, 0.5, 1.0]
    assert sc.percentile_ranks([5, 5, 5]) == [0.5, 0.5, 0.5]
    assert sc.percentile_ranks([None, 2, 4]) == [None, 0.0, 1.0]
    assert sc.percentile_ranks([7]) == [0.5]


def _item(i, channel_id=1, **kw):
    d = dict(video_id=i, channel_id=channel_id, has_data=True, exposure_days=10, views=100 * i,
             watch_time_minutes=500.0 * i, avg_view_pct=10.0 * i, retention_avg=0.1 * i, subs=i, likes=10 * i,
             comments=i, title=f"v{i}")
    d.update(kw)
    return d


def test_scoring_needs_cohort_and_uses_more_than_views():
    items = [_item(i) for i in range(1, 6)]
    sc.score_videos(items)
    by = {i["video_id"]: i for i in items}
    assert by[5]["label"] == "strong" and by[5]["score"] > 85
    assert by[1]["label"] == "weak" and by[1]["weak_reasons"]
    assert all(set(i["components"]) == set(sc.WEIGHTS) for i in items)

    # high views but terrible watch time/retention must NOT win on views alone
    items = [_item(i) for i in range(1, 5)]
    items.append(_item(9, views=10_000, watch_time_minutes=1.0, avg_view_pct=1.0, retention_avg=0.01,
                       subs=0, likes=0, comments=0))
    sc.score_videos(items)
    clickbait = next(i for i in items if i["video_id"] == 9)
    assert clickbait["label"] == "weak"


def test_scoring_states_for_young_unsynced_and_small_cohorts():
    items = [_item(1, exposure_days=1), _item(2, has_data=False), _item(3), _item(4)]
    sc.score_videos(items)
    assert [i["label"] for i in items] == ["too_new", "not_synced", "insufficient_data", "insufficient_data"]
    assert all(i["score"] is None for i in items)
    # videos of different channels are never ranked against each other
    mixed = [_item(i, channel_id=1 + i % 2) for i in range(1, 7)]
    sc.score_videos(mixed)
    assert all(i["score"] is None for i in mixed)  # 3 per channel < MIN_COHORT


def test_retention_summary_and_interpolation():
    pts = [[x / 100, 1 - x / 200] for x in range(1, 101)]
    assert sc.retention_at(pts, 0.5) == pytest.approx(0.75, abs=0.01)
    s = sc.retention_summary(pts)
    assert s["at_50"] == pytest.approx(0.75, abs=0.01) and s["steepest_drop"] is None
    cliff = [[0.1, 1.0], [0.2, 0.4], [0.3, 0.38], [1.0, 0.3]]
    assert sc.retention_summary(cliff)["steepest_drop"]["delta"] < -0.5
    assert sc.retention_summary([])["average"] is None
    assert sc.average_curves([[[0.5, 1.0]], [[0.5, 0.5]]]) == [[0.5, 0.75]]


def test_recommendations_refuse_to_guess_without_data():
    recs = sc.build_recommendations(topics=[], durations=[], posting={"by_hour": []}, retention=None,
                                    weak_videos=[], scored_videos=1, days_since_upload=None)
    assert [r["kind"] for r in recs] == ["need_data"]


# ============================================================ sync
def test_sync_stores_real_rows_with_source_and_state(ch1, http, yt):
    yt.video_views_per_day = {"AAA": 100}
    with SessionLocal() as db:
        vid = add_video(db, ch1["id"], "AAA", days_ago=10)
    res = sync(ch1["id"], http)
    assert res.status == "ok" and res.videos_synced == 1 and res.retention_synced == 1
    with SessionLocal() as db:
        days = db.scalars(select(AnalyticsDaily).where(AnalyticsDaily.channel_id == ch1["id"])).all()
        assert days and all(d.data_source == DataSource.YOUTUBE_API for d in days)
        assert max(d.day for d in days) == TODAY - timedelta(days=1)   # never invented for "today"
        assert days[0].views == 100 and days[0].watch_time_minutes == 450.0
        vrows = db.scalars(select(AnalyticsVideo).where(AnalyticsVideo.video_id == vid)).all()
        assert min(r.day for r in vrows) >= TODAY - timedelta(days=10)    # clamped to publication
        snap = db.scalar(select(AnalyticsChannelSnapshot))
        assert snap.subscribers == 1234 and snap.day == TODAY
        assert len(db.scalar(select(AnalyticsRetention.points))) == 100
        st = db.get(AnalyticsSyncState, ch1["id"])
        assert st.status.value == "ok" and st.synced_through == TODAY - timedelta(days=1)


def test_resync_is_idempotent_and_takes_revised_numbers(ch1, http, yt):
    yt.video_views_per_day = {"AAA": 100}
    with SessionLocal() as db:
        add_video(db, ch1["id"], "AAA", days_ago=10)
    sync(ch1["id"], http)
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(AnalyticsDaily))
    yt.revision = 5          # YouTube revises recent days
    yt.calls.clear()
    sync(ch1["id"], http)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AnalyticsDaily)) == before   # no duplicates
        latest = db.scalar(select(AnalyticsDaily).order_by(AnalyticsDaily.day.desc()).limit(1))
        assert latest.views == 105
    # incremental: the second sync only asked for the overlap window, not the whole history
    chan_call = next(c for c in yt.calls if "filters" not in c)
    assert date.fromisoformat(chan_call["startDate"]) >= TODAY - timedelta(days=1 + get_settings().analytics_overlap_days)


def test_hidden_subscriber_count_is_not_reported_as_zero(ch1, http, yt):
    yt.hidden = True
    sync(ch1["id"], http)
    with SessionLocal() as db:
        snap = db.scalar(select(AnalyticsChannelSnapshot))
        assert snap.subscribers is None and snap.subscribers_hidden is True


def test_missing_analytics_scope_is_reported_without_calling_youtube(ch1, http, yt):
    with SessionLocal() as db:
        cred = db.scalar(select(YoutubeCredential))
        cred.scopes = ["https://www.googleapis.com/auth/youtube.upload"]
        db.commit()
    res = sync(ch1["id"], http)
    assert res.status == "error" and res.error_kind == "scope" and yt.calls == []
    with SessionLocal() as db:
        assert db.get(AnalyticsSyncState, ch1["id"]).error_kind == "scope"


def test_forbidden_report_is_a_scope_error_and_isolated_per_channel(channel, http, yt):
    a, b = channel("chan-a", "Chan A"), channel("chan-b", "Chan B")
    with SessionLocal() as db:
        connect_channel(db, a["id"])
        connect_channel(db, b["id"])
    yt.report_error = (403, "forbidden")
    ra = sync(a["id"], http)
    assert ra.status == "error" and ra.error_kind == "scope"
    yt.report_error = None
    rb = sync(b["id"], http)
    assert rb.status == "ok"                       # channel A's failure did not touch channel B
    with SessionLocal() as db:
        assert db.get(AnalyticsSyncState, a["id"]).status.value == "error"
        assert db.get(AnalyticsSyncState, b["id"]).status.value == "ok"


def test_quota_error_sets_retry_after(ch1, http, yt):
    yt.report_error = (403, "quotaExceeded")
    res = sync(ch1["id"], http)
    assert res.error_kind == "quota"
    with SessionLocal() as db:
        st = db.get(AnalyticsSyncState, ch1["id"])
        assert st.retry_after is not None and st.retry_after > datetime.now(timezone.utc)


def test_one_broken_video_gives_partial_not_failure(ch1, http, yt):
    yt.video_views_per_day = {"GOOD": 50, "BAD": 50}
    yt.video_errors = {"BAD": (404, "notFound")}
    with SessionLocal() as db:
        good = add_video(db, ch1["id"], "GOOD")
        add_video(db, ch1["id"], "BAD")
    res = sync(ch1["id"], http)
    assert res.status == "partial" and res.videos_synced == 1 and res.videos_failed == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AnalyticsVideo).where(AnalyticsVideo.video_id == good)) > 0


def test_retention_skipped_for_young_videos_and_when_youtube_has_no_curve(ch1, http, yt):
    yt.video_views_per_day = {"NEW": 10, "OLD": 10}
    yt.no_retention = {"OLD"}
    with SessionLocal() as db:
        add_video(db, ch1["id"], "NEW", days_ago=1)
        add_video(db, ch1["id"], "OLD", days_ago=30)
    res = sync(ch1["id"], http)
    assert res.retention_synced == 0
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AnalyticsRetention)) == 0   # nothing invented


def test_disconnected_or_paused_channels_are_skipped(channel, http, yt):
    ch = channel("chan-x", "Chan X")
    assert sync(ch["id"], http).status == "skipped" and yt.calls == []


# ============================================================ API: KPI honesty
def test_summary_without_sync_says_not_synced_not_zero(client, ch1):
    s = client.get("/api/analytics/summary").json()
    assert s["data_state"] == "not_synced"
    assert s["kpis"]["views"]["value"] is None and s["kpis"]["views"]["source"] == "not_synced"
    assert s["subscribers_total"]["value"] is None
    assert s["sync"]["not_synced"] == 1
    ov = client.get("/api/overview").json()
    assert ov["total_views"]["value"] is None and ov["total_subscribers"]["source"] == "not_synced"


def test_summary_after_sync_has_real_numbers_and_growth(client, ch1, http, yt):
    yt.video_views_per_day = {"AAA": 100}
    with SessionLocal() as db:
        add_video(db, ch1["id"], "AAA", days_ago=80)
    sync(ch1["id"], http)
    end = TODAY - timedelta(days=1)
    s = client.get("/api/analytics/summary", params={"channel_id": ch1["id"], "start": str(end - timedelta(days=6)),
                                                    "end": str(end)}).json()
    assert s["data_state"] == "synced"
    assert s["kpis"]["views"]["value"] == 700 and s["kpis"]["views"]["source"] == "youtube_api"
    assert s["kpis"]["views"]["previous"] == 700 and s["kpis"]["views"]["change_pct"] == 0.0
    assert s["kpis"]["watch_time_minutes"]["value"] == pytest.approx(3150)
    assert s["kpis"]["average_view_percentage"]["value"] == pytest.approx(42.5)
    assert s["kpis"]["subscribers_net"]["value"] == 7 * (2 - 0)      # 100//50 gained, 100//200 lost
    assert s["subscribers_total"]["value"] == 1234 and s["subscribers_total"]["source"] == "youtube_api"
    assert s["production"]["videos_published"] == 1
    assert s["top_video"]["youtube_video_id"] == "AAA"
    assert client.get("/api/overview").json()["total_subscribers"]["value"] == 1234


def test_data_of_one_channel_never_leaks_into_another(client, channel, http, yt):
    a, b = channel("chan-a", "Chan A"), channel("chan-b", "Chan B")
    with SessionLocal() as db:
        connect_channel(db, a["id"])
        connect_channel(db, b["id"])
        add_video(db, a["id"], "AAA")
    yt.video_views_per_day = {"AAA": 40}
    sync(a["id"], http)
    sa = client.get("/api/analytics/summary", params={"channel_id": a["id"]}).json()
    sb = client.get("/api/analytics/summary", params={"channel_id": b["id"]}).json()
    assert sa["kpis"]["views"]["value"] > 0
    assert sb["kpis"]["views"]["value"] is None and sb["top_video"] is None
    assert client.get("/api/analytics/summary", params={"channel_id": 9999}).status_code == 404


def test_range_validation(client, ch1):
    r = client.get("/api/analytics/summary", params={"start": "2026-02-01", "end": "2026-01-01"})
    assert r.status_code == 422
    assert client.get("/api/analytics/summary", params={"video_status": "nope"}).status_code == 422
    assert client.get("/api/analytics/timeseries", params={"granularity": "year"}).status_code == 422


# ============================================================ API: charts
def test_timeseries_buckets_and_split(client, channel, http, yt):
    a, b = channel("chan-a", "Chan A"), channel("chan-b", "Chan B")
    with SessionLocal() as db:
        connect_channel(db, a["id"])
        connect_channel(db, b["id"])
    yt.video_views_per_day = {"x": 10}
    sync(a["id"], http)
    yt.video_views_per_day = {"x": 30}
    sync(b["id"], http)
    end = TODAY - timedelta(days=1)
    p = {"start": str(end - timedelta(days=27)), "end": str(end)}
    day = client.get("/api/analytics/timeseries", params={**p, "granularity": "day", "split": "true"}).json()
    assert len(day["points"]) == 28 and day["points"][0]["views"] == 40
    assert {s["channel_name"] for s in day["by_channel"]} == {"Chan A", "Chan B"}
    assert day["points"][-1]["preliminary"] is True and day["points"][0]["preliminary"] is False
    week = client.get("/api/analytics/timeseries", params={**p, "granularity": "week"}).json()
    assert all(date.fromisoformat(w["period"]).weekday() == 0 for w in week["points"])
    assert sum(w["views"] for w in week["points"]) == 28 * 40
    month = client.get("/api/analytics/timeseries", params={**p, "granularity": "month"}).json()
    assert sum(m["views"] for m in month["points"]) == 28 * 40


def test_compare_channels_ranks_by_watch_time_and_reports_growth(client, channel, http, yt):
    a, b, c = channel("chan-a", "Chan A"), channel("chan-b", "Chan B"), channel("chan-c", "Chan C")
    with SessionLocal() as db:
        for x in (a, b):
            connect_channel(db, x["id"])
    yt.video_views_per_day = {"x": 10}
    sync(a["id"], http)
    yt.video_views_per_day = {"x": 30}
    sync(b["id"], http)
    end = TODAY - timedelta(days=1)
    r = client.get("/api/analytics/channels/compare",
                   params={"start": str(end - timedelta(days=6)), "end": str(end)}).json()
    rows = {x["channel_name"]: x for x in r["items"]}
    assert r["best"]["channel_name"] == "Chan B" and r["best"]["basis"] == "watch_time_minutes"
    assert rows["Chan B"]["views"] == 210 and rows["Chan A"]["views"] == 70
    assert rows["Chan B"]["views_growth_pct"] == 0.0           # previous 7 days had the same constant rate
    assert rows["Chan C"]["views"] is None and rows["Chan C"]["source"] == "not_synced"   # no fake zero for channel C


def test_distribution_shares_sum_to_100(client, channel, http, yt):
    a, b = channel("chan-a", "Chan A"), channel("chan-b", "Chan B")
    with SessionLocal() as db:
        connect_channel(db, a["id"])
        connect_channel(db, b["id"])
    yt.video_views_per_day = {"x": 10}
    sync(a["id"], http)
    yt.video_views_per_day = {"x": 30}
    sync(b["id"], http)
    d = client.get("/api/analytics/distribution", params={"by": "channel"}).json()
    assert [i["label"] for i in d["items"]] == ["Chan B", "Chan A"]
    assert d["items"][0]["share"] == 75.0 and d["items"][1]["share"] == 25.0
    assert client.get("/api/analytics/distribution", params={"by": "x"}).status_code == 422


# ============================================================ API: videos, filters, insights
def seed_cohort(channel_id, http, yt, n=6, content_types=None):
    """n videos with increasing quality, all old enough to be scored."""
    ids = []
    with SessionLocal() as db:
        for i in range(1, n + 1):
            ct = (content_types or [ContentType.RAIN_SOUNDS] * n)[i - 1]
            ids.append(add_video(db, channel_id, f"V{i}", days_ago=20, minutes=60 if i % 2 else 120,
                                 content_type=ct, theme=f"theme {ct.value}", title=f"Video {i}"))
    yt.video_views_per_day = {f"V{i}": 20 * i for i in range(1, n + 1)}
    sync(channel_id, http)
    return ids


def test_video_list_scores_labels_and_filters(client, ch1, http, yt):
    types = [ContentType.RAIN_SOUNDS] * 3 + [ContentType.COZY_AMBIENCE] * 3
    seed_cohort(ch1["id"], http, yt, 6, types)
    r = client.get("/api/analytics/videos", params={"channel_id": ch1["id"], "sort": "views"}).json()
    items = r["items"]
    assert [i["youtube_video_id"] for i in items] == [f"V{i}" for i in range(6, 0, -1)]
    assert all(i["source"] == "youtube_api" and i["score_source"] == "calculated" for i in items)
    assert items[0]["views"] > items[-1]["views"] and items[0]["has_retention"] is True
    by_score = client.get("/api/analytics/videos", params={"channel_id": ch1["id"]}).json()["items"]
    assert by_score[0]["score"] >= by_score[-1]["score"]
    assert {i["label"] for i in by_score} <= {"strong", "average", "weak"}
    # topic filter works through the content project
    rain = client.get("/api/analytics/videos", params={"channel_id": ch1["id"], "topic": "rain_sounds"}).json()
    assert {i["content_type"] for i in rain["items"]} == {"rain_sounds"} and rain["total"] == 3
    # status filter
    with SessionLocal() as db:
        v = db.scalar(select(Video).where(Video.youtube_video_id == "V1"))
        v.privacy_status = PrivacyStatus.PRIVATE
        db.commit()
    priv = client.get("/api/analytics/videos", params={"video_status": "private"}).json()
    assert [i["youtube_video_id"] for i in priv["items"]] == ["V1"]


def test_unsynced_video_is_shown_as_not_synced(client, ch1, http, yt):
    with SessionLocal() as db:
        add_video(db, ch1["id"], "LONELY")
    it = client.get("/api/analytics/videos").json()["items"][0]
    assert it["label"] == "not_synced" and it["views"] is None and it["data_state"] == "not_synced"


def test_filtered_summary_uses_video_table(client, ch1, http, yt):
    types = [ContentType.RAIN_SOUNDS] * 3 + [ContentType.COZY_AMBIENCE] * 3
    seed_cohort(ch1["id"], http, yt, 6, types)
    end = TODAY - timedelta(days=1)
    p = {"channel_id": ch1["id"], "start": str(end - timedelta(days=6)), "end": str(end)}
    allv = client.get("/api/analytics/summary", params=p).json()
    rain = client.get("/api/analytics/summary", params={**p, "topic": "rain_sounds"}).json()
    assert rain["basis"] == "videos" and allv["basis"] == "channel"
    assert rain["kpis"]["views"]["value"] == 7 * (20 + 40 + 60)
    assert allv["kpis"]["views"]["value"] == 7 * sum(20 * i for i in range(1, 7))
    ts = client.get("/api/analytics/timeseries", params={**p, "topic": "cozy_ambience"}).json()
    assert ts["basis"] == "videos" and ts["points"][0]["views"] == 20 * (4 + 5 + 6)


def test_retention_endpoints(client, ch1, http, yt):
    ids = seed_cohort(ch1["id"], http, yt, 2)
    r = client.get(f"/api/analytics/videos/{ids[0]}/retention").json()
    assert r["data_state"] == "synced" and len(r["points"]) == 100 and r["summary"]["at_50"] is not None
    avg = client.get("/api/analytics/retention", params={"channel_id": ch1["id"]}).json()
    assert avg["n_videos"] == 2 and avg["summary"]["at_25"] > avg["summary"]["at_75"]
    with SessionLocal() as db:
        lone = add_video(db, ch1["id"], "NORET", days_ago=1)
    n = client.get(f"/api/analytics/videos/{lone}/retention").json()
    assert n["data_state"] == "not_synced" and n["points"] == []
    assert client.get("/api/analytics/videos/99999/retention").status_code == 404


def test_insights_compare_topics_and_recommend(client, ch1, http, yt):
    # rain videos are strong (high ids), cozy videos weak: views/day = 20*i
    types = [ContentType.COZY_AMBIENCE] * 3 + [ContentType.RAIN_SOUNDS] * 3
    seed_cohort(ch1["id"], http, yt, 6, types)
    ins = client.get("/api/analytics/insights", params={"channel_id": ch1["id"]}).json()
    topics = {t["key"]: t for t in ins["topics"]}
    assert topics["rain_sounds"]["avg_score"] > topics["cozy_ambience"]["avg_score"]
    assert ins["videos_scored"] == 6 and ins["source"] == "calculated"
    rec = next(r for r in ins["recommendations"] if r["kind"] == "topic")
    assert rec["suggested_content_type"] == "rain_sounds" and rec["evidence"]["best"] == "rain_sounds"
    assert {d["minutes"] for d in ins["durations"]} == {60, 120}
    assert ins["underperformers"] == [] or all(u["reasons"] for u in ins["underperformers"])
    assert len(ins["posting_times"]["by_hour"]) == 24 and len(ins["posting_times"]["by_weekday"]) == 7


def test_insights_without_data_ask_for_data(client, ch1):
    ins = client.get("/api/analytics/insights", params={"channel_id": ch1["id"]}).json()
    assert [r["kind"] for r in ins["recommendations"]] == ["need_data"]


def test_posting_time_needs_full_first_week_of_data(ch1, http, yt):
    with SessionLocal() as db:
        add_video(db, ch1["id"], "OLDV", days_ago=30)
        add_video(db, ch1["id"], "FRESH", days_ago=3)
    yt.video_views_per_day = {"OLDV": 10, "FRESH": 10}
    sync(ch1["id"], http)
    with SessionLocal() as db:
        ins = svc.insights(db, svc.make_scope(ch1["id"], default_days=90))
    assert ins["posting_times"]["measured_videos"] == 1     # FRESH has no complete 7-day window


# ============================================================ sync queue + worker
def test_sync_endpoint_queues_once_and_requires_connection(client, channel, ch1):
    r = client.post(f"/api/channels/{ch1['id']}/analytics/sync")
    assert r.status_code == 202 and r.json()["queued"] is True
    again = client.post(f"/api/channels/{ch1['id']}/analytics/sync").json()
    assert again["queued"] is False and again["job_id"] == r.json()["job_id"]
    other = channel("chan-noconn", "No connection")
    assert client.post(f"/api/channels/{other['id']}/analytics/sync").status_code == 409
    assert client.post(f"/api/channels/{ch1['id']}/analytics/sync", params={"backfill_days": 99999}).status_code == 422
    all_ = client.post("/api/analytics/sync").json()
    assert all_["queued"] == 0 and len(all_["results"]) == 2        # nothing fatal for the unconnected one


def test_worker_runs_queued_job_and_releases_dedupe_key(client, ch1, http, yt):
    yt.video_views_per_day = {"AAA": 25}
    with SessionLocal() as db:
        add_video(db, ch1["id"], "AAA")
    job_id = client.post(f"/api/channels/{ch1['id']}/analytics/sync").json()["job_id"]
    assert AnalyticsWorker(http=http).run(once=True) == 0
    with SessionLocal() as db:
        job = db.get(SchedulerJob, job_id)
        assert job.status == JobStatus.SUCCEEDED and job.dedupe_key is None
        assert db.get(AnalyticsSyncState, ch1["id"]).status.value == "ok"
    st = client.get("/api/analytics/sync").json()
    assert st["channels"][0]["state"] == "synced"
    # a new sync can be queued after the previous one finished
    assert client.post(f"/api/channels/{ch1['id']}/analytics/sync").json()["queued"] is True


def test_interrupted_job_is_requeued_after_restart(ch1):
    with SessionLocal() as db:
        job, _ = analytics_sync.enqueue_sync(db, ch1["id"])
    assert analytics_sync.claim_job("w1") is not None
    assert analytics_sync.claim_job("w2") is None            # no double processing
    assert analytics_sync.recover_running_jobs() == 1
    assert analytics_sync.claim_job("w3") is not None


def test_automatic_schedule_respects_interval_errors_and_pause(client, channel, ch1, http, yt):
    paused = channel("chan-paused", "Paused")
    with SessionLocal() as db:
        connect_channel(db, paused["id"])
        db.get(Channel, paused["id"]).enabled = False
        db.commit()
        assert analytics_sync.enqueue_due_channels(db) == 1          # only the active, never-synced channel
    sync(ch1["id"], http)
    with SessionLocal() as db:
        db.query(SchedulerJob).delete()
        db.commit()
        assert analytics_sync.enqueue_due_channels(db) == 0          # just synced: not due yet
        st = db.get(AnalyticsSyncState, ch1["id"])
        st.last_attempt_at = datetime.now(timezone.utc) - timedelta(hours=7)
        st.status, st.error_kind = st.status.__class__("error"), "scope"
        cred = db.scalar(select(YoutubeCredential).where(YoutubeCredential.channel_id == ch1["id"]))
        cred.updated_at = datetime.now(timezone.utc) - timedelta(hours=8)   # connected before the failed sync
        db.commit()
        assert analytics_sync.enqueue_due_channels(db) == 0          # scope errors wait for a reconnect
        cred = db.scalar(select(YoutubeCredential).where(YoutubeCredential.channel_id == ch1["id"]))
        cred.updated_at = datetime.now(timezone.utc)                  # user reconnected the channel
        db.commit()
        assert analytics_sync.enqueue_due_channels(db) == 1


def test_overview_endpoint_stays_compatible(client, ch1, http, yt):
    yt.video_views_per_day = {"AAA": 10}
    sync(ch1["id"], http)
    ov = client.get("/api/overview").json()
    assert ov["total_views"]["source"] == "youtube_api" and ov["daily_views"]
    assert ov["total_subscribers"]["value"] == 1234
