"""Phase 3: YouTube OAuth, publishing queue, resumable upload, retry/recovery.

Google/YouTube are simulated with httpx.MockTransport (no network, no real credentials).
"""
import json
import re
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select, text

from app.core import storage
from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.integrations.youtube import oauth
from app.models import Channel, PublishingJob, Video, YoutubeCredential
from app.models.enums import CredentialStatus, JobStatus
from app.services import youtube_service
from app.worker.publisher import PublishWorker, next_quota_reset, prepare_thumbnail
from conftest import make_png

VIDEO_BYTES = 600 * 1024  # > 2 chunks of 256 KiB


class FakeYouTube:
    """Minimal stateful YouTube + Google OAuth simulation."""

    def __init__(self):
        self.received = 0
        self.size = 0
        self.session_started = 0
        self.fail_chunk_with: int | None = None
        self.start_error: tuple[int, str] | None = None
        self.thumb_error: tuple[int, str] | None = None
        self.refresh_error = False
        self.thumb_calls = 0
        self.playlist_calls = 0
        self.metadata: dict | None = None
        self.log: list[str] = []
        self.yt_channel = {"id": "UC_test_1", "snippet": {"title": "My Cozy Channel"}}
        self.code_has_refresh = True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url, method = str(request.url), request.method
        self.log.append(f"{method} {url.split('?')[0]}")
        if url.startswith("https://oauth2.googleapis.com/token"):
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            if form["grant_type"] == "refresh_token":
                if self.refresh_error:
                    return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Token revoked"})
                return httpx.Response(200, json={"access_token": "ya29.new", "expires_in": 3600})
            body = {"access_token": "ya29.first", "expires_in": 3600, "scope": " ".join(oauth.SCOPES)}
            if self.code_has_refresh:
                body["refresh_token"] = "1//refresh-secret"
            return httpx.Response(200, json=body)
        if url.startswith("https://oauth2.googleapis.com/revoke"):
            return httpx.Response(200)
        if "/youtube/v3/channels" in url:
            return httpx.Response(200, json={"items": [self.yt_channel]})
        if "/youtube/v3/playlists" in url:
            return httpx.Response(200, json={"items": [{"id": "PL1", "snippet": {"title": "Rain"},
                                                        "status": {"privacyStatus": "public"}}]})
        if "/upload/youtube/v3/videos" in url and method == "POST":
            if self.start_error:
                return self._err(*self.start_error)
            self.session_started += 1
            self.metadata = json.loads(request.content)
            self.size = int(request.headers["x-upload-content-length"])
            self.received = 0
            return httpx.Response(200, headers={"location": "https://upload.example/session1"})
        if url.startswith("https://upload.example/session1"):
            return self._chunk(request)
        if "/thumbnails/set" in url:
            self.thumb_calls += 1
            if self.thumb_error:
                return self._err(*self.thumb_error)
            return httpx.Response(200, json={})
        if "/playlistItems" in url:
            self.playlist_calls += 1
            return httpx.Response(200, json={"id": "PLI1"})
        return httpx.Response(404, json={"error": {"message": "unexpected " + url}})

    @staticmethod
    def _err(status: int, reason: str) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": reason, "errors": [{"reason": reason}]}})

    def _chunk(self, request: httpx.Request) -> httpx.Response:
        cr = request.headers["content-range"]
        if cr.startswith("bytes */"):  # status query
            if self.received >= self.size > 0:
                return httpx.Response(200, json={"id": "YT_VID_1"})
            h = {"range": f"bytes=0-{self.received - 1}"} if self.received else {}
            return httpx.Response(308, headers=h)
        if self.fail_chunk_with:
            code, self.fail_chunk_with = self.fail_chunk_with, None
            return httpx.Response(code, json={"error": {"message": "backend", "errors": [{"reason": "backendError"}]}})
        m = re.match(r"bytes (\d+)-(\d+)/(\d+)", cr)
        start, end, total = map(int, m.groups())
        assert start == self.received, f"chunk starts at {start}, server has {self.received}"
        self.received = end + 1
        if self.received >= total:
            return httpx.Response(200, json={"id": "YT_VID_1"})
        return httpx.Response(308, headers={"range": f"bytes=0-{end}"})


@pytest.fixture
def yt():
    return FakeYouTube()


@pytest.fixture
def http(yt):
    c = httpx.Client(transport=httpx.MockTransport(yt))
    yield c
    c.close()


@pytest.fixture(autouse=True)
def oauth_env(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "client-id")
    monkeypatch.setattr(s, "google_client_secret", "client-secret")
    monkeypatch.setattr(s, "youtube_upload_chunk_mb", 0)  # -> 256 KiB chunks
    monkeypatch.setattr(s, "publish_retry_base_sec", 60)


def connect_channel(db, channel_id, yt_id=None, expired=False, status=CredentialStatus.VALID):
    exp = time.time() - 10 if expired else time.time() + 3000
    db.add(YoutubeCredential(
        channel_id=channel_id, youtube_channel_id=yt_id or f"UC_{channel_id}", youtube_channel_title="T",
        scopes=oauth.SCOPES, status=status, token_expiry=datetime.now(timezone.utc),
        token_encrypted={"access_token": "ya29.old", "refresh_token": "1//r", "expires_at": exp, "scope": ""}))
    db.commit()


def make_video(db, channel_id, title="Rain 1h", passed=True, thumb=True):
    d = storage.channel_dir(channel_id) / "videos" / "x"
    d.mkdir(parents=True, exist_ok=True)
    (d / "video.mp4").write_bytes(b"\0" * VIDEO_BYTES)
    rel = (d / "video.mp4").relative_to(storage.storage_root()).as_posix()
    trel = None
    if thumb:
        (d / "thumb.png").write_bytes(make_png(size=(1280, 720)))
        trel = (d / "thumb.png").relative_to(storage.storage_root()).as_posix()
    v = Video(channel_id=channel_id, title=title, file_path=rel, duration_sec=3600, width=1920, height=1080,
              fps=30, size_bytes=VIDEO_BYTES, thumbnail_path=trel, qc_report={"passed": passed})
    db.add(v)
    db.commit()
    return v.id


@pytest.fixture
def setup(client, channel):
    """channel with connected YouTube + one rendered video."""
    ch = channel("cozy", "Cozy")
    with SessionLocal() as db:
        connect_channel(db, ch["id"])
        vid = make_video(db, ch["id"])
    return ch, vid


def publish(client, ch, vid, **kw):
    return client.post(f"/api/channels/{ch['id']}/publishing/jobs", json={"video_id": vid, **kw})


def job_row(job_id):
    with SessionLocal() as db:
        j = db.get(PublishingJob, job_id)
        db.expunge(j)
        return j


# ============================================================ OAuth / connection
def test_connect_requires_configuration(client, channel, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "")
    ch = channel()
    r = client.post(f"/api/channels/{ch['id']}/youtube/connect")
    assert r.status_code == 503 and "GOOGLE_CLIENT_ID" in r.json()["detail"]
    assert client.get("/api/youtube/config").json()["configured"] is False


def test_auth_url_and_state_is_bound_to_channel(client, channel):
    ch = channel()
    url = client.post(f"/api/channels/{ch['id']}/youtube/connect").json()["auth_url"]
    assert url.startswith("https://accounts.google.com/") and "access_type=offline" in url
    state = re.search(r"state=([^&]+)", url).group(1)
    from urllib.parse import unquote
    assert oauth.read_state(unquote(state)) == ch["id"]
    with pytest.raises(oauth.OAuthError):
        oauth.read_state("garbage")


def test_callback_connects_channel_and_encrypts_token(client, channel, http, yt):
    ch = channel()
    state = oauth.make_state(ch["id"])
    with SessionLocal() as db:
        youtube_service.complete_connect(db, "auth-code", state, http)
    st = client.get(f"/api/channels/{ch['id']}/youtube").json()
    assert st["connected"] is True and st["youtube_channel_title"] == "My Cozy Channel"
    assert client.get(f"/api/channels/{ch['id']}").json()["status"] == "active"
    with engine.connect() as c:  # tokens are never plaintext at rest
        raw = c.execute(text("SELECT token_encrypted FROM youtube_credentials")).scalar()
    assert b"refresh-secret" not in bytes(raw) and b"ya29" not in bytes(raw)


def test_same_youtube_channel_cannot_link_two_coco_channels(client, channel, http):
    a, b = channel("a", "A"), channel("b", "B")
    with SessionLocal() as db:
        youtube_service.complete_connect(db, "c", oauth.make_state(a["id"]), http)
    with SessionLocal() as db, pytest.raises(Exception) as ei:
        youtube_service.complete_connect(db, "c", oauth.make_state(b["id"]), http)
    assert "đã được kết nối" in str(ei.value)


def test_missing_refresh_token_is_rejected(client, channel, http, yt):
    yt.code_has_refresh = False
    ch = channel()
    with SessionLocal() as db, pytest.raises(Exception) as ei:
        youtube_service.complete_connect(db, "c", oauth.make_state(ch["id"]), http)
    assert "refresh token" in str(ei.value)


def test_callback_route_handles_denied_and_bad_state(client, channel):
    ch = channel()
    state = oauth.make_state(ch["id"])
    r = client.get("/api/youtube/oauth/callback", params={"error": "access_denied", "state": state},
                   follow_redirects=False)
    assert r.status_code == 303 and f"/channels/{ch['id']}?youtube=error" in r.headers["location"]
    r = client.get("/api/youtube/oauth/callback", params={"code": "x", "state": "bad"}, follow_redirects=False)
    assert r.status_code == 303 and "youtube=error" in r.headers["location"]


def test_disconnect(client, channel, http):
    ch = channel()
    with SessionLocal() as db:
        youtube_service.complete_connect(db, "c", oauth.make_state(ch["id"]), http)
        youtube_service.disconnect(db, db.get(Channel, ch["id"]), http)
    assert client.get(f"/api/channels/{ch['id']}/youtube").json()["connected"] is False
    assert client.get(f"/api/channels/{ch['id']}").json()["status"] == "disconnected"
    assert client.post(f"/api/channels/{ch['id']}/youtube/disconnect").status_code == 400


# ============================================================ creating jobs
def test_default_private_and_defaults_from_project(client, setup):
    ch, vid = setup
    r = publish(client, ch, vid, title="Rainy Study Session 1h", tags=["rain", "study", "rain"])
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["privacy_status"] == "private" and j["status"] == "queued"
    assert j["tags"] == ["rain", "study"] and j["history"][0]["event"] == "created"
    # same video cannot be queued twice
    assert publish(client, ch, vid).status_code == 409


def test_create_validations(client, channel, setup):
    ch, vid = setup
    other = channel("other", "Other")
    with SessionLocal() as db:
        ovid = make_video(db, other["id"])
    # another channel's video is invisible here, other channel is not connected
    assert publish(client, ch, ovid).status_code == 404
    assert publish(client, other, ovid).status_code == 409
    with SessionLocal() as db:
        bad = make_video(db, ch["id"], passed=False)
    assert "kiểm tra chất lượng" in publish(client, ch, bad).json()["detail"]
    assert publish(client, ch, vid, title="x" * 101).status_code == 422
    assert publish(client, ch, vid, title="a<b").status_code == 422
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert publish(client, ch, vid, publish_at=past).status_code == 422


def test_scheduled_publish_forces_private(client, setup):
    ch, vid = setup
    when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    j = publish(client, ch, vid, privacy="public", publish_at=when).json()
    assert j["privacy_status"] == "private" and j["publish_at"]


def test_next_slot_scheduling(client, setup):
    ch, vid = setup
    assert publish(client, ch, vid, use_next_slot=True).status_code == 409  # no schedule yet
    sched = {"timezone": "Asia/Ho_Chi_Minh", "slots": [{"weekday": d, "time": "20:00"} for d in range(7)]}
    assert client.patch(f"/api/channels/{ch['id']}", json={"publish_schedule": sched}).status_code == 200
    slots = client.get(f"/api/channels/{ch['id']}/publishing/slots", params={"count": 3}).json()
    assert len(slots["slots"]) == 3 and slots["timezone"] == "Asia/Ho_Chi_Minh"
    j = publish(client, ch, vid, use_next_slot=True).json()
    assert j["publish_at"].startswith(slots["slots"][0][:16])
    # that slot is now taken -> the next suggestion moves on
    assert client.get(f"/api/channels/{ch['id']}/publishing/slots").json()["slots"][0] != slots["slots"][0]


# ============================================================ worker: happy path
def test_upload_end_to_end(client, setup, http, yt):
    ch, vid = setup
    j = publish(client, ch, vid, title="Rain 1h", tags=["rain"], playlist_id="PL1", description="d").json()
    assert PublishWorker(http).run(once=True) == 0
    done = client.get(f"/api/publishing/jobs/{j['id']}").json()
    assert done["status"] == "succeeded", done["last_error"]
    assert done["youtube_video_id"] == "YT_VID_1" and done["youtube_url"].endswith("YT_VID_1")
    assert yt.received == VIDEO_BYTES and yt.thumb_calls == 1 and yt.playlist_calls == 1
    assert yt.metadata["status"]["privacyStatus"] == "private"
    assert yt.metadata["snippet"]["title"] == "Rain 1h"
    events = [h["event"] for h in done["history"]]
    assert events[:2] == ["created", "started"] and "uploaded" in events and events[-1] == "succeeded"
    with SessionLocal() as db:
        v = db.get(Video, vid)
        assert v.youtube_video_id == "YT_VID_1" and v.privacy_status.value == "private"
    # a published video cannot be published again
    assert publish(client, ch, vid).status_code == 409


def test_scheduled_upload_sends_publish_at(client, setup, http, yt):
    ch, vid = setup
    when = datetime.now(timezone.utc) + timedelta(days=3)
    publish(client, ch, vid, publish_at=when.isoformat())
    PublishWorker(http).run(once=True)
    assert yt.metadata["status"]["privacyStatus"] == "private"
    assert yt.metadata["status"]["publishAt"].endswith("Z")


def test_upload_after_is_respected(client, setup, http, yt):
    ch, vid = setup
    later = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    j = publish(client, ch, vid, upload_after=later).json()
    assert PublishWorker(http).claim() is None
    assert client.get(f"/api/publishing/jobs/{j['id']}").json()["status"] == "queued"


# ============================================================ retry / recovery
def test_network_error_retries_with_backoff_and_resumes(client, setup, http, yt):
    ch, vid = setup
    j = publish(client, ch, vid).json()
    yt.fail_chunk_with = 503
    PublishWorker(http).run(once=True)
    row = job_row(j["id"])
    assert row.status == JobStatus.QUEUED and row.attempts == 1 and row.last_error
    assert row.next_attempt_at > datetime.now(timezone.utc) and row.upload_session_uri
    # not due yet -> worker leaves it alone
    assert PublishWorker(http).claim() is None
    with SessionLocal() as db:
        db.get(PublishingJob, j["id"]).next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    PublishWorker(http).run(once=True)
    assert yt.session_started == 1, "must resume the same session, not start a new upload"
    done = job_row(j["id"])
    assert done.status == JobStatus.SUCCEEDED and done.attempts == 2


def test_gives_up_after_max_attempts_and_flags_only_that_channel(client, channel, setup, http, yt):
    ch, vid = setup
    other = channel("other", "Other")
    j = publish(client, ch, vid).json()
    with SessionLocal() as db:
        db.get(PublishingJob, j["id"]).max_attempts = 1
        db.commit()
    yt.start_error = (500, "backendError")
    PublishWorker(http).run(once=True)
    assert job_row(j["id"]).status == JobStatus.FAILED
    assert client.get(f"/api/channels/{ch['id']}").json()["status"] == "error"
    assert client.get(f"/api/channels/{other['id']}").json()["status"] == "disconnected"  # untouched
    # user retries after fixing the problem
    yt.start_error = None
    assert client.post(f"/api/publishing/jobs/{j['id']}/retry").json()["status"] == "queued"
    PublishWorker(http).run(once=True)
    assert job_row(j["id"]).status == JobStatus.SUCCEEDED
    assert client.get(f"/api/channels/{ch['id']}").json()["last_error"] is None


def test_permanent_error_fails_without_retry(client, setup, http, yt):
    ch, vid = setup
    j = publish(client, ch, vid).json()
    yt.start_error = (400, "invalidTitle")
    PublishWorker(http).run(once=True)
    row = job_row(j["id"])
    assert row.status == JobStatus.FAILED and row.attempts == 1 and "invalidTitle" in row.last_error


def test_quota_exceeded_waits_for_reset_without_using_attempt(client, setup, http, yt):
    ch, vid = setup
    j = publish(client, ch, vid).json()
    yt.start_error = (403, "quotaExceeded")
    PublishWorker(http).run(once=True)
    row = job_row(j["id"])
    assert row.status == JobStatus.QUEUED and row.attempts == 0
    assert row.next_attempt_at > datetime.now(timezone.utc) + timedelta(minutes=1)
    assert next_quota_reset() > datetime.now(timezone.utc)


def test_revoked_token_parks_only_that_channel(client, channel, setup, http, yt):
    ch, vid = setup
    other = channel("other", "Other")
    with SessionLocal() as db:
        connect_channel(db, other["id"])
        ovid = make_video(db, other["id"], title="Other video")
        # expire the first channel's access token so the worker must refresh it
        c = db.scalar(select(YoutubeCredential).where(YoutubeCredential.channel_id == ch["id"]))
        c.token_encrypted = {**c.token_encrypted, "expires_at": time.time() - 100}
        db.commit()
    j1 = publish(client, ch, vid).json()
    j2 = publish(client, other, ovid).json()
    yt.refresh_error = True
    w = PublishWorker(http)
    w.run(once=True)
    r1 = job_row(j1["id"])
    assert r1.status == JobStatus.QUEUED and r1.attempts == 0, "parked, attempt not consumed"
    st = client.get(f"/api/channels/{ch['id']}/youtube").json()
    assert st["status"] == "revoked" and st["connected"] is False
    assert client.get(f"/api/channels/{ch['id']}").json()["status"] == "error"
    # the other channel keeps working
    yt.refresh_error = False
    PublishWorker(http).run(once=True)
    assert job_row(j2["id"]).status == JobStatus.SUCCEEDED
    assert job_row(j1["id"]).status == JobStatus.QUEUED  # still waiting for reconnect
    # creating a new job for a disconnected channel is refused
    assert publish(client, ch, make_video_for(ch["id"])).status_code == 409


def make_video_for(channel_id):
    with SessionLocal() as db:
        return make_video(db, channel_id, title="another")


def test_thumbnail_rejection_does_not_fail_published_video(client, setup, http, yt):
    ch, vid = setup
    yt.thumb_error = (403, "forbidden")
    j = publish(client, ch, vid).json()
    PublishWorker(http).run(once=True)
    row = job_row(j["id"])
    assert row.status == JobStatus.SUCCEEDED and "thumbnail" in row.last_error
    assert row.youtube_video_id == "YT_VID_1"


def test_post_step_failure_never_reuploads(client, setup, http, yt):
    """Video uploaded, thumbnail hits a transient error -> retry must only redo the thumbnail."""
    ch, vid = setup
    yt.thumb_error = (503, "backendError")
    j = publish(client, ch, vid).json()
    PublishWorker(http).run(once=True)
    row = job_row(j["id"])
    assert row.status == JobStatus.QUEUED and row.youtube_video_id == "YT_VID_1"
    yt.thumb_error = None
    with SessionLocal() as db:
        db.get(PublishingJob, j["id"]).next_attempt_at = None
        db.commit()
    PublishWorker(http).run(once=True)
    assert yt.session_started == 1
    assert job_row(j["id"]).status == JobStatus.SUCCEEDED


def test_crash_recovery_resumes_from_youtube_offset(client, setup, http, yt):
    ch, vid = setup
    j = publish(client, ch, vid).json()
    # simulate: previous worker started the session, sent 2 chunks, then died while RUNNING
    yt.size, yt.received = VIDEO_BYTES, 2 * 256 * 1024
    with SessionLocal() as db:
        row = db.get(PublishingJob, j["id"])
        row.status = JobStatus.RUNNING
        row.attempts = 1
        row.upload_session_uri = "https://upload.example/session1"
        row.bytes_uploaded = 0  # progress write was lost in the crash
        db.commit()
    w = PublishWorker(http)
    assert w.recover_orphans() == 1
    assert job_row(j["id"]).status == JobStatus.QUEUED
    w.run_job(w.claim())
    assert yt.session_started == 0 and yt.received == VIDEO_BYTES
    assert job_row(j["id"]).status == JobStatus.SUCCEEDED


def test_paused_channel_jobs_wait(client, setup, http, yt):
    ch, vid = setup
    j = publish(client, ch, vid).json()
    with SessionLocal() as db:
        db.get(Channel, ch["id"]).enabled = False
        db.commit()
    assert PublishWorker(http).claim() is None
    assert job_row(j["id"]).status == JobStatus.QUEUED


def test_cancel_and_retry_rules(client, setup):
    ch, vid = setup
    j = publish(client, ch, vid).json()
    assert client.post(f"/api/publishing/jobs/{j['id']}/retry").status_code == 409
    c = client.post(f"/api/publishing/jobs/{j['id']}/cancel").json()
    assert c["status"] == "cancelled"
    assert client.post(f"/api/publishing/jobs/{j['id']}/cancel").status_code == 409
    assert client.post(f"/api/publishing/jobs/{j['id']}/retry").json()["status"] == "queued"
    st = client.get("/api/publishing/status").json()
    assert st["counts"]["queued"] == 1


def test_list_jobs_filters_by_channel(client, channel, setup):
    ch, vid = setup
    publish(client, ch, vid)
    other = channel("other", "Other")
    assert len(client.get("/api/publishing/jobs", params={"channel_id": ch["id"]}).json()) == 1
    assert client.get("/api/publishing/jobs", params={"channel_id": other["id"]}).json() == []


def test_prepare_thumbnail_shrinks_large_images(tmp_path):
    from PIL import Image
    import os
    p = tmp_path / "big.png"
    Image.frombytes("RGB", (2400, 1400), os.urandom(2400 * 1400 * 3)).save(p)
    assert p.stat().st_size > 2 * 1024 * 1024
    data, mime = prepare_thumbnail(p)
    assert mime == "image/jpeg" and len(data) <= 2 * 1024 * 1024
