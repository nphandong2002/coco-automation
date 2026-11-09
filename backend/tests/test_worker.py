"""Render queue + worker integration tests. Real FFmpeg renders (short durations)."""
import threading
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core import storage
from app.core.database import SessionLocal
from app.models import Asset, Channel, ContentProject, Video, VideoJob
from app.models.enums import JobStatus
from app.worker.runner import RenderWorker
from conftest import has_ffmpeg

pytestmark = pytest.mark.skipif(not has_ffmpeg(), reason="ffmpeg not available")


def _ready_project(client, channel, background, character_with_art, code="cozy-study", **kw):
    ch = channel(code, code.title())
    char = character_with_art(ch["id"])
    bg = background(ch["id"])
    body = {
        "title": "Rainy pomodoro", "content_type": "pomodoro", "duration_minutes": 30,
        "background_asset_id": bg["id"], "character_id": char["id"], "setting": "attic",
        "animation": {"background_motion": "slow_zoom", "effects": ["rain", "vignette"],
                      "character": {"position": "bottom_right", "scale": 0.4, "motion": "bob"}},
        "audio_layers": [{"kind": "generator", "generator": "rain", "volume": 0.7},
                         {"kind": "generator", "generator": "fireplace", "volume": 0.4}],
        "pomodoro": {"focus_min": 5, "short_break_min": 5, "long_break_min": 5, "cycles_before_long": 2},
        "render_settings": {"overlay": {"mode": "pomodoro"}, "chime": True, "resolution": "1280x720"},
        **kw,
    }
    r = client.post(f"/api/channels/{ch['id']}/content", json=body)
    assert r.status_code == 201, r.text
    return ch, r.json()


def _render(client, ch, p, **kw):
    r = client.post(f"/api/channels/{ch['id']}/content/{p['id']}/render", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def test_preview_render_end_to_end(client, channel, background, character_with_art):
    ch, p = _ready_project(client, channel, background, character_with_art)
    job = _render(client, ch, p, job_type="preview", preview_seconds=12)
    assert job["status"] == "queued" and job["job_type"] == "preview"
    # duplicate active job for the same project is refused
    assert client.post(f"/api/channels/{ch['id']}/content/{p['id']}/render",
                       json={"job_type": "preview"}).status_code == 409

    assert RenderWorker().run(once=True) == 0
    j = client.get(f"/api/production/jobs/{job['id']}").json()
    assert j["status"] == "succeeded", j["error"]
    assert j["output_url"].endswith("video.mp4") and j["has_log"]
    out = storage.resolve(j["output_url"].removeprefix("/media/"))
    assert out.exists() and out.stat().st_size > 10_000
    # previews never create a `videos` row nor change the project status
    assert client.get("/api/production/videos").json() == []
    assert client.get(f"/api/channels/{ch['id']}/content/{p['id']}").json()["status"] == "draft"
    status = client.get("/api/production/status").json()
    assert status["succeeded_24h"] == 1 and status["workers"][0]["state"] == "stopped"


def test_full_render_creates_video_with_qc(client, channel, background, character_with_art):
    # loop mode (no timer overlay) → the 30-minute video is assembled by stream copy
    ch, p = _ready_project(client, channel, background, character_with_art,
                           render_settings={"overlay": {"mode": "none"}, "resolution": "1280x720"}, pomodoro=None)
    job = _render(client, ch, p, job_type="full")
    assert client.get(f"/api/channels/{ch['id']}/content/{p['id']}").json()["status"] == "queued"
    RenderWorker().run(once=True)
    j = client.get(f"/api/production/jobs/{job['id']}").json()
    assert j["status"] == "succeeded", j["error"]
    videos = client.get("/api/production/videos", params={"channel_id": ch["id"]}).json()
    assert len(videos) == 1
    v = videos[0]
    assert v["qc_passed"] and abs(v["duration_sec"] - 1800) < 2
    assert (v["width"], v["height"], v["fps"]) == (1280, 720, 30.0)
    checks = {c["name"]: c["ok"] for c in v["qc_report"]["checks"]}
    assert checks["video_codec"] and checks["audio_sample_rate"] and checks["audio_not_silent"]
    assert v["thumbnail_url"] and v["sha256"]
    proj = client.get(f"/api/channels/{ch['id']}/content/{p['id']}").json()
    assert proj["status"] == "rendered" and proj["video_count"] == 1
    # editing a rendered project is allowed and resets it to draft
    assert client.delete(f"/api/production/videos/{v['id']}").status_code == 204
    assert client.get(f"/api/channels/{ch['id']}/content/{p['id']}").json()["status"] == "ready"


def test_cancel_queued_and_paused_channel_waits(client, channel, background, character_with_art):
    ch, p = _ready_project(client, channel, background, character_with_art)
    job = _render(client, ch, p, job_type="full")
    r = client.post(f"/api/production/jobs/{job['id']}/cancel")
    assert r.json()["status"] == "cancelled"
    assert client.get(f"/api/channels/{ch['id']}/content/{p['id']}").json()["status"] == "ready"
    # paused channel: job stays queued, worker skips it
    client.post(f"/api/channels/{ch['id']}/pause")
    job2 = client.post(f"/api/production/jobs/{job['id']}/retry").json()
    w = RenderWorker()
    assert w._acquire_lock()
    try:
        assert w.claim() is None
    finally:
        w._release_lock()
    assert client.get(f"/api/production/jobs/{job2['id']}").json()["status"] == "queued"


def test_failure_marks_only_that_channel(client, channel, background, character_with_art):
    ch, p = _ready_project(client, channel, background, character_with_art, code="broken-ch")
    other, op = _ready_project(client, channel, background, character_with_art, code="healthy-ch")
    job = _render(client, ch, p, job_type="preview", preview_seconds=10)
    # break the snapshot: background file disappears after queueing
    with SessionLocal() as db:
        a = db.get(Asset, p["background_asset_id"])
        storage.resolve(a.file_path).unlink()
    RenderWorker().run(once=True)
    j = client.get(f"/api/production/jobs/{job['id']}").json()
    assert j["status"] == "failed" and j["error"]
    assert client.get(f"/api/channels/{ch['id']}").json()["status"] != "error"   # previews don't flag
    # a failed FULL job flags ITS channel only (inserted directly: the API would refuse, file is missing)
    with SessionLocal() as db:
        jf = VideoJob(channel_id=ch["id"], content_project_id=p["id"], status=JobStatus.QUEUED,
                      render_config=db.get(VideoJob, job["id"]).render_config | {"job_type": "full"},
                      duration_sec=10, timeout_sec=600, max_attempts=1)
        db.add(jf)
        db.commit()
    RenderWorker().run(once=True)
    assert client.get(f"/api/channels/{ch['id']}").json()["status"] == "error"
    assert client.get(f"/api/channels/{other['id']}").json()["status"] != "error"
    assert client.get(f"/api/channels/{ch['id']}/content/{p['id']}").json()["status"] == "failed"


def test_orphan_recovery_and_single_render_lock(client, channel, background, character_with_art):
    ch, p = _ready_project(client, channel, background, character_with_art)
    job = _render(client, ch, p, job_type="full")
    with SessionLocal() as db:   # simulate a worker that died mid-render
        j = db.get(VideoJob, job["id"])
        j.status, j.attempts, j.worker_id = JobStatus.RUNNING, 1, "dead:1"
        j.heartbeat_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        db.commit()
    w1 = RenderWorker()
    assert w1._acquire_lock()
    try:
        w2 = RenderWorker()
        assert not w2._acquire_lock()          # only one renderer at a time
        assert w1.recover_orphans() == 1
    finally:
        w1._release_lock()
    with SessionLocal() as db:
        j = db.get(VideoJob, job["id"])
        assert j.status == JobStatus.QUEUED and "Khôi phục" in j.step
        assert db.get(ContentProject, p["id"]).status.value == "queued"


def test_cancel_running_job(client, channel, background, character_with_art):
    ch, p = _ready_project(client, channel, background, character_with_art)
    job = _render(client, ch, p, job_type="full")   # pomodoro overlay → long re-encode, cancellable
    w = RenderWorker()

    def cancel_soon():
        import time
        for _ in range(200):
            time.sleep(0.2)
            with SessionLocal() as db:
                j = db.get(VideoJob, job["id"])
                if j.status == JobStatus.RUNNING and j.progress > 0.02:
                    break
        client.post(f"/api/production/jobs/{job['id']}/cancel")

    t = threading.Thread(target=cancel_soon)
    t.start()
    w.run(once=True)
    t.join()
    with SessionLocal() as db:
        j = db.get(VideoJob, job["id"])
        assert j.status == JobStatus.CANCELLED
        assert db.scalar(select(Video)) is None
        assert db.get(Channel, ch["id"]).last_error is None
