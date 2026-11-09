"""Phase 5: monitoring snapshot, alerts, hung-job watchdog, maintenance, RAM guard, monitor worker."""
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import psutil
import pytest
from sqlalchemy import func, select

from app.core import storage
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import (
    ContentProject,
    PublishingJob,
    SchedulerJob,
    SystemLog,
    SystemMetric,
    Video,
    VideoJob,
    WorkerStatus,
)
from app.models.enums import ContentType, JobStatus, LogLevel, WorkerState
from app.services import monitor_service, recovery
from app.worker.monitor import MonitorWorker
from app.worker.runner import RenderWorker
from test_analytics import add_video

NOW = lambda: datetime.now(timezone.utc)  # noqa: E731
AGO = lambda **kw: NOW() - timedelta(**kw)  # noqa: E731


def add_worker(db, kind, pid, hostname=None, state=WorkerState.IDLE, job=None, age=0):
    import socket
    w = WorkerStatus(worker_id=f"{hostname or socket.gethostname()}:{pid}:{kind}", kind=kind,
                     hostname=hostname or socket.gethostname(), pid=pid, state=state, current_job_id=job,
                     started_at=AGO(minutes=5), heartbeat_at=AGO(seconds=age), info={})
    db.add(w)
    db.commit()
    return w


def add_render_job(db, channel_id, heartbeat_age=0, runtime=60, timeout=3600):
    p = ContentProject(channel_id=channel_id, title="p", content_type=ContentType.RAIN_SOUNDS, fingerprint=__import__("uuid").uuid4().hex)
    db.add(p)
    db.flush()
    j = VideoJob(channel_id=channel_id, content_project_id=p.id, status=JobStatus.RUNNING, timeout_sec=timeout,
                 started_at=AGO(seconds=runtime), heartbeat_at=AGO(seconds=heartbeat_age))
    db.add(j)
    db.commit()
    return j.id


@pytest.fixture
def ch(channel):
    return channel("cozy", "Cozy Study")


# ============================================================ snapshot + alerts
def test_snapshot_reports_real_measurements(client, ch):
    snap = client.get("/api/monitoring").json()
    h = snap["host"]
    assert 0 <= h["cpu_percent"] <= 100 and h["ram_total_gb"] > 0 and h["disk_free_gb"] > 0
    assert h["ram_available_mb"] == pytest.approx(psutil.virtual_memory().available / 1024**2, rel=0.5)
    assert snap["database"]["ok"] is True and snap["database"]["latency_ms"] >= 0
    assert [w["kind"] for w in snap["workers"]] == ["render", "publish", "analytics", "monitor"]
    assert snap["queues"]["render"]["queued"] == 0
    assert snap["config"]["secret_key_configured"] is True


def test_workers_never_started_raise_alerts_and_overall_status(client, ch):
    snap = client.get("/api/monitoring").json()
    codes = {a["code"] for a in snap["alerts"]}
    assert {"worker_render_offline", "worker_publish_offline", "worker_analytics_offline",
            "worker_monitor_offline"} <= codes
    assert snap["status"] in ("warning", "critical")
    assert all(w["state"] == "never_started" and not w["online"] for w in snap["workers"])


def test_online_workers_clear_alerts_and_waiting_jobs_escalate(client, ch):
    with SessionLocal() as db:
        for k in ("render", "publish", "analytics", "monitor"):
            add_worker(db, k, pid=1000 + len(k))
    snap = client.get("/api/monitoring").json()
    assert not [a for a in snap["alerts"] if a["code"].startswith("worker_")]
    # a stale worker with queued work is CRITICAL, without work only a warning
    with SessionLocal() as db:
        db.query(WorkerStatus).filter(WorkerStatus.kind == "render").update({"heartbeat_at": AGO(minutes=30)})
        db.commit()
        add_video(db, ch["id"], "V1")
        p = ContentProject(channel_id=ch["id"], title="q", content_type=ContentType.RAIN_SOUNDS, fingerprint="fpq")
        db.add(p)
        db.flush()
        db.add(VideoJob(channel_id=ch["id"], content_project_id=p.id, status=JobStatus.QUEUED))
        db.commit()
    snap = client.get("/api/monitoring").json()
    a = next(a for a in snap["alerts"] if a["code"] == "worker_render_offline")
    assert a["severity"] == "critical" and "1 tác vụ" in a["message"]
    assert snap["queues"]["render"]["queued"] == 1 and snap["status"] == "critical"


def test_disk_thresholds(client, monkeypatch):
    import app.services.monitor_service as ms
    s = get_settings()
    free = ms.host_metrics()["disk_free_gb"]
    monkeypatch.setattr(s, "min_free_disk_gb", free + 5)
    assert "disk_critical" in {a["code"] for a in client.get("/api/monitoring").json()["alerts"]}
    monkeypatch.setattr(s, "min_free_disk_gb", 0.1)
    monkeypatch.setattr(s, "disk_warn_gb", free + 5)
    codes = {a["code"] for a in client.get("/api/monitoring").json()["alerts"]}
    assert "disk_low" in codes and "disk_critical" not in codes


def test_youtube_health_section(client, ch):
    with SessionLocal() as db:
        from test_youtube import connect_channel
        from app.models.enums import CredentialStatus
        connect_channel(db, ch["id"], status=CredentialStatus.REVOKED)
        db.add(SystemLog(category="youtube", level=LogLevel.ERROR, message="Token bị thu hồi", channel_id=ch["id"]))
        db.add(SystemLog(category="publishing", level=LogLevel.INFO, message="ok"))
        db.commit()
    yt = client.get("/api/monitoring").json()["youtube"]
    assert yt["credentials"]["revoked"] == 1
    assert yt["errors_24h"] == [{"category": "youtube", "level": "error", "count": 1, "last_at": yt["errors_24h"][0]["last_at"]}]
    assert yt["recent_errors"][0]["message"] == "Token bị thu hồi"
    assert "youtube_reconnect" in {a["code"] for a in client.get("/api/monitoring").json()["alerts"]}


# ============================================================ stalled-job detection
def test_find_stalled_for_every_job_kind(ch):
    s = get_settings()
    with SessionLocal() as db:
        healthy = add_render_job(db, ch["id"], heartbeat_age=5)
        dead_hb = add_render_job(db, ch["id"], heartbeat_age=s.worker_stale_seconds + 60)
        over = add_render_job(db, ch["id"], heartbeat_age=5, runtime=3600 + 600, timeout=3600)
        vid = add_video(db, ch["id"], "V1")
        db.add(PublishingJob(channel_id=ch["id"], video_id=vid, status=JobStatus.RUNNING, title="t"))
        db.commit()
        pj = db.scalar(select(PublishingJob))
        pj.updated_at = AGO(seconds=s.publish_stall_seconds + 60)
        db.add(SchedulerJob(channel_id=ch["id"], job_type="analytics_sync", status=JobStatus.RUNNING,
                            locked_at=AGO(hours=2), timeout_sec=1800, dedupe_key="analytics_sync:1"))
        db.commit()
        found = {(x.kind, x.job_id) for x in recovery.find_stalled(db)}
        assert ("render", healthy) not in found
        assert {("render", dead_hb), ("render", over)} <= found
        assert ("publish", pj.id) in found and any(k == "analytics" for k, _ in found)


def test_fresh_jobs_are_not_stalled(ch):
    with SessionLocal() as db:
        add_render_job(db, ch["id"], heartbeat_age=2)
        vid = add_video(db, ch["id"], "V1")
        db.add(PublishingJob(channel_id=ch["id"], video_id=vid, status=JobStatus.RUNNING, title="t"))
        db.commit()
        assert recovery.find_stalled(db) == []


# ============================================================ watchdog
def _spawn_fake_worker():
    # the cmdline contains "app.worker", which is how the watchdog recognises our own worker processes
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", "app.worker"])


def test_watchdog_terminates_hung_worker_and_records_it(ch, monkeypatch):
    monkeypatch.setattr(get_settings(), "watchdog_kill_grace_seconds", 3)
    proc = _spawn_fake_worker()
    try:
        with SessionLocal() as db:
            job = add_render_job(db, ch["id"], heartbeat_age=get_settings().worker_stale_seconds + 60)
            add_worker(db, "render", proc.pid, state=WorkerState.RENDERING, job=job)
            actions = recovery.watchdog(db)
            assert len(actions) == 1 and str(proc.pid) in actions[0]
            w = db.scalar(select(WorkerStatus).where(WorkerStatus.kind == "render"))
            assert w.state == WorkerState.STOPPED
            log = db.scalar(select(SystemLog).where(SystemLog.category == "watchdog"))
            assert log.level == LogLevel.ERROR and log.details["job_id"] == job
        assert proc.wait(timeout=10) is not None     # the hung process is gone
    finally:
        if proc.poll() is None:
            proc.kill()


def test_watchdog_never_kills_a_process_that_is_not_our_worker(ch):
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])   # no "app.worker" in cmdline
    try:
        with SessionLocal() as db:
            job = add_render_job(db, ch["id"], heartbeat_age=999)
            add_worker(db, "render", proc.pid, state=WorkerState.RENDERING, job=job)
            actions = recovery.watchdog(db)
            assert actions and "đã chết" in actions[0]
        assert proc.poll() is None                       # PID reuse safety: untouched
    finally:
        proc.kill()


def test_watchdog_ignores_other_hosts_and_reports_missing_owner(ch):
    with SessionLocal() as db:
        job = add_render_job(db, ch["id"], heartbeat_age=999)
        assert "không thấy worker" in recovery.watchdog(db)[0]
        add_worker(db, "render", pid=1, hostname="another-host", state=WorkerState.RENDERING, job=job)
        assert "đã chết" in recovery.watchdog(db)[0]      # foreign host: only the row is marked, nothing is killed


def test_hung_job_is_requeued_by_worker_startup_recovery(ch):
    """Watchdog kills the worker; the restarted worker's existing recovery re-queues the job (end to end)."""
    with SessionLocal() as db:
        job = add_render_job(db, ch["id"], heartbeat_age=999)
    assert RenderWorker().recover_orphans() == 1
    with SessionLocal() as db:
        j = db.get(VideoJob, job)
        assert j.status == JobStatus.QUEUED and "Khôi phục" in j.step


# ============================================================ maintenance
def test_maintenance_prunes_old_data_but_keeps_recent(ch):
    s = get_settings()
    with SessionLocal() as db:
        db.add_all([SystemLog(category="x", message="old", created_at=AGO(days=s.log_retention_days + 5)),
                    SystemLog(category="x", message="new")])
        db.add_all([SystemMetric(ts=AGO(days=s.metrics_retention_days + 1), cpu_percent=1, ram_percent=1,
                                 ram_available_mb=1, disk_free_gb=1),
                    SystemMetric(ts=AGO(minutes=1), cpu_percent=1, ram_percent=1, ram_available_mb=1, disk_free_gb=1)])
        db.add(WorkerStatus(worker_id="h:1:render", kind="render", hostname="h", pid=1, state=WorkerState.STOPPED,
                            started_at=AGO(days=3), heartbeat_at=AGO(days=2), info={}))
        db.add(SchedulerJob(job_type="analytics_sync", status=JobStatus.SUCCEEDED, finished_at=AGO(days=40)))
        db.commit()
        report = recovery.maintenance(db)
        assert report["system_logs_deleted"] == 1 and report["metrics_deleted"] == 1
        assert report["worker_rows_deleted"] == 1 and report["scheduler_jobs_deleted"] == 1
        assert [m for (m,) in db.execute(select(SystemLog.message).where(SystemLog.category == "x"))] == ["new"]
        assert db.scalar(select(func.count()).select_from(SystemMetric)) == 1


def test_maintenance_removes_stale_tmp_files_unless_a_render_runs(ch):
    tmp = storage.tmp_dir() / "jobs" / "77"
    tmp.mkdir(parents=True, exist_ok=True)
    old, fresh = tmp / "old.bin", tmp / "fresh.bin"
    old.write_bytes(b"x" * 1000)
    fresh.write_bytes(b"y")
    t = time.time() - 3 * 86400
    import os
    os.utime(old, (t, t))
    with SessionLocal() as db:
        add_render_job(db, ch["id"], heartbeat_age=1)
        assert recovery.maintenance(db)["tmp_skipped"]       # render running: tmp untouched
        assert old.exists()
        db.query(VideoJob).update({"status": JobStatus.SUCCEEDED})
        db.commit()
        rep = recovery.maintenance(db)
        assert rep["tmp_files_deleted"] == 1 and rep["tmp_bytes_freed"] == 1000
    assert not old.exists() and fresh.exists()


def test_maintenance_and_watchdog_endpoints(client, ch):
    assert client.post("/api/monitoring/maintenance").status_code == 200
    assert client.post("/api/monitoring/watchdog").json() == {"actions": []}


# ============================================================ sampling + worker + RAM guard
def test_monitor_worker_tick_samples_and_heartbeats(client, ch):
    MonitorWorker().run(once=True)
    with SessionLocal() as db:
        m = db.scalar(select(SystemMetric))
        assert m is not None and m.ram_available_mb > 0
        w = db.scalar(select(WorkerStatus).where(WorkerStatus.kind == "monitor"))
        assert w.state == WorkerState.STOPPED               # clean shutdown recorded
    h = client.get("/api/monitoring/history", params={"hours": 1}).json()
    assert len(h["points"]) == 1 and h["points"][0]["cpu"] >= 0
    assert client.get("/api/monitoring/history", params={"hours": 0}).status_code == 422


def test_only_one_monitor_instance(monkeypatch):
    a = MonitorWorker()
    assert a._acquire_lock() is True
    try:
        assert MonitorWorker()._acquire_lock() is False
    finally:
        a._release_lock()


def test_render_worker_holds_back_when_ram_is_low(monkeypatch):
    s = get_settings()
    w = RenderWorker()
    assert w._ram_ok() is True
    monkeypatch.setattr(s, "min_free_ram_mb", 10**9)       # impossible requirement
    assert w._ram_ok() is False
    monkeypatch.setattr(s, "min_free_ram_mb", 1)
    assert w._ram_ok() is True
