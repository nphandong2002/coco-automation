"""System monitoring: one snapshot of the host, workers, queues, YouTube health and database, plus alerts.

Everything is measured (psutil / SQL) — nothing is simulated. `alerts` turns the measurements into
actionable warnings; `status` is the worst severity.
"""
from __future__ import annotations

import os
import shutil
import socket
import time
from datetime import datetime, timedelta, timezone

import psutil
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import check_database
from app.core.storage import storage_root
from app.models import (
    AnalyticsSyncState,
    Channel,
    PublishingJob,
    SchedulerJob,
    SystemLog,
    SystemMetric,
    VideoJob,
    WorkerStatus,
    YoutubeCredential,
)
from app.models.enums import CredentialStatus, JobStatus, LogLevel, SyncStatus, WorkerState
from app.services import recovery
from app.services.analytics_sync import JOB_TYPE as ANALYTICS_JOB

EXPECTED_WORKERS = ("render", "publish", "analytics", "monitor")
SEVERITY = {"ok": 0, "warning": 1, "critical": 2}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- host
def host_metrics() -> dict:
    root = storage_root()
    mem, swap, disk = psutil.virtual_memory(), psutil.swap_memory(), shutil.disk_usage(root)
    try:
        load = [round(x, 2) for x in os.getloadavg()]
    except (AttributeError, OSError):  # Windows
        load = None
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.2), "cpu_count": psutil.cpu_count(),
        "load_avg": load,
        "ram_total_gb": round(mem.total / 1024**3, 1), "ram_percent": mem.percent,
        "ram_available_mb": int(mem.available / 1024**2),
        "swap_percent": swap.percent if swap.total else None,
        "disk_total_gb": round(disk.total / 1024**3, 1), "disk_free_gb": round(disk.free / 1024**3, 1),
        "disk_percent": round((disk.total - disk.free) / disk.total * 100, 1) if disk.total else 0,
        "storage_dir": str(root), "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
    }


def process_metrics() -> dict:
    """FFmpeg processes (the heavy ones) and the RAM used by our own API/worker processes."""
    ff, app_rss, app_n = [], 0, 0
    now = time.time()
    for p in psutil.process_iter(["pid", "name", "cmdline", "memory_info", "create_time"]):
        try:
            name = (p.info["name"] or "").lower()
            cmd = " ".join(p.info["cmdline"] or [])
            rss = (p.info["memory_info"].rss if p.info["memory_info"] else 0)
            if name.startswith("ffmpeg"):
                ff.append({"pid": p.info["pid"], "rss_mb": int(rss / 1024**2),
                           "elapsed_sec": int(now - p.info["create_time"]), "cmd": cmd[:160]})
            elif "app.worker" in cmd or "app.main" in cmd:
                app_rss += rss
                app_n += 1
        except (psutil.Error, OSError):
            continue
    return {"ffmpeg": ff, "ffmpeg_rss_mb": sum(f["rss_mb"] for f in ff),
            "app_processes": app_n, "app_rss_mb": int(app_rss / 1024**2)}


# ---------------------------------------------------------------- workers & queues
def _workers(db: Session) -> list[dict]:
    s = get_settings()
    now = _now()
    latest: dict[str, WorkerStatus] = {}
    for w in db.scalars(select(WorkerStatus).order_by(WorkerStatus.heartbeat_at)).all():
        latest[w.kind] = w  # newest heartbeat wins
    out = []
    for kind in EXPECTED_WORKERS:
        w = latest.get(kind)
        age = int((now - w.heartbeat_at).total_seconds()) if w else None
        online = bool(w and w.state != WorkerState.STOPPED and age is not None and age <= s.worker_stale_seconds)
        out.append({"kind": kind, "online": online, "state": w.state.value if w else "never_started",
                    "worker_id": w.worker_id if w else None, "pid": w.pid if w else None,
                    "current_job_id": w.current_job_id if w else None, "heartbeat_age_sec": age,
                    "started_at": w.started_at if w else None})
    return out


def _queues(db: Session) -> dict:
    now = _now()
    since = now - timedelta(hours=24)

    def n(model, *conds) -> int:  # noqa: ANN001, ANN002
        return int(db.scalar(select(func.count()).select_from(model).where(*conds)) or 0)

    def oldest(model, ts_col, *conds) -> int | None:  # noqa: ANN001, ANN002
        v = db.scalar(select(func.min(ts_col)).where(*conds))
        return int((now - v).total_seconds()) if v else None

    return {
        "render": {"queued": n(VideoJob, VideoJob.status == JobStatus.QUEUED),
                   "running": n(VideoJob, VideoJob.status == JobStatus.RUNNING),
                   "failed_24h": n(VideoJob, VideoJob.status == JobStatus.FAILED, VideoJob.finished_at >= since),
                   "succeeded_24h": n(VideoJob, VideoJob.status == JobStatus.SUCCEEDED, VideoJob.finished_at >= since),
                   "oldest_queued_sec": oldest(VideoJob, VideoJob.created_at, VideoJob.status == JobStatus.QUEUED)},
        "upload": {"queued": n(PublishingJob, PublishingJob.status == JobStatus.QUEUED),
                   "running": n(PublishingJob, PublishingJob.status == JobStatus.RUNNING),
                   "waiting_retry": n(PublishingJob, PublishingJob.status == JobStatus.QUEUED,
                                      PublishingJob.next_attempt_at > now),
                   "failed_24h": n(PublishingJob, PublishingJob.status == JobStatus.FAILED,
                                   PublishingJob.updated_at >= since),
                   "succeeded_24h": n(PublishingJob, PublishingJob.status == JobStatus.SUCCEEDED,
                                      PublishingJob.updated_at >= since),
                   "oldest_queued_sec": oldest(PublishingJob, PublishingJob.created_at,
                                               PublishingJob.status == JobStatus.QUEUED)},
        "analytics": {"queued": n(SchedulerJob, SchedulerJob.job_type == ANALYTICS_JOB,
                                  SchedulerJob.status == JobStatus.QUEUED),
                      "running": n(SchedulerJob, SchedulerJob.job_type == ANALYTICS_JOB,
                                   SchedulerJob.status == JobStatus.RUNNING)},
    }


# ---------------------------------------------------------------- youtube + database
def _youtube(db: Session) -> dict:
    since = _now() - timedelta(hours=24)
    creds = {"valid": 0, "expired": 0, "revoked": 0}
    for status, c in db.execute(select(YoutubeCredential.status, func.count()).group_by(YoutubeCredential.status)).all():
        creds[status.value] = c
    rows = db.execute(
        select(SystemLog.category, SystemLog.level, func.count(), func.max(SystemLog.created_at))
        .where(SystemLog.created_at >= since, SystemLog.category.in_(["youtube", "publishing", "analytics", "watchdog"]),
               SystemLog.level.in_([LogLevel.WARNING, LogLevel.ERROR]))
        .group_by(SystemLog.category, SystemLog.level)).all()
    recent = db.scalars(
        select(SystemLog).where(SystemLog.created_at >= since, SystemLog.category.in_(["youtube", "publishing", "analytics"]),
                                SystemLog.level.in_([LogLevel.WARNING, LogLevel.ERROR]))
        .order_by(SystemLog.created_at.desc()).limit(8)).all()
    sync_errors = db.execute(
        select(Channel.id, Channel.name, AnalyticsSyncState.error_kind, AnalyticsSyncState.last_error,
               AnalyticsSyncState.retry_after)
        .join(Channel, Channel.id == AnalyticsSyncState.channel_id)
        .where(AnalyticsSyncState.status == SyncStatus.ERROR)).all()
    now = _now()
    quota_parked = int(db.scalar(select(func.count()).select_from(AnalyticsSyncState).where(
        AnalyticsSyncState.retry_after > now)) or 0)
    return {
        "credentials": creds,
        "errors_24h": [{"category": c, "level": lv.value, "count": n, "last_at": last} for c, lv, n, last in rows],
        "recent_errors": [{"at": l.created_at, "category": l.category, "level": l.level.value, "message": l.message,
                           "channel_id": l.channel_id} for l in recent],
        "sync_errors": [{"channel_id": i, "channel_name": nm, "kind": k, "error": (e or "")[:200],
                         "retry_after": ra} for i, nm, k, e, ra in sync_errors],
        "quota_parked": quota_parked,
    }


def _database(db: Session) -> dict:
    ok, msg = check_database()
    if not ok:
        return {"ok": False, "message": msg}
    t = time.perf_counter()
    db.execute(text("SELECT 1"))
    latency = round((time.perf_counter() - t) * 1000, 1)
    out: dict = {"ok": True, "message": msg, "latency_ms": latency}
    try:
        out["size_mb"] = round(db.scalar(text("SELECT pg_database_size(current_database())")) / 1024**2, 1)
        out["connections"] = int(db.scalar(text(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")) or 0)
    except Exception:  # noqa: BLE001 - non-fatal extras
        db.rollback()
    return out


# ---------------------------------------------------------------- alerts
def _alert(sev: str, code: str, message: str, hint: str = "") -> dict:
    return {"severity": sev, "code": code, "message": message, "hint": hint}


def build_alerts(snap: dict) -> list[dict]:
    s = get_settings()
    a: list[dict] = []
    h, q, db, yt = snap["host"], snap["queues"], snap["database"], snap["youtube"]
    if not db["ok"]:
        a.append(_alert("critical", "database_down", f"Database không phản hồi: {db['message']}",
                        "sudo systemctl status postgresql"))
    if h["disk_free_gb"] < s.min_free_disk_gb:
        a.append(_alert("critical", "disk_critical", f"Ổ đĩa chỉ còn {h['disk_free_gb']} GB — render sẽ bị từ chối",
                        "Xóa video cũ ở Video Production hoặc thêm dung lượng"))
    elif h["disk_free_gb"] < s.disk_warn_gb:
        a.append(_alert("warning", "disk_low", f"Ổ đĩa còn {h['disk_free_gb']} GB (cảnh báo dưới {s.disk_warn_gb:g} GB)",
                        "Một video 8 giờ có thể chiếm vài GB"))
    if h["ram_percent"] >= s.ram_warn_percent:
        a.append(_alert("warning", "ram_high", f"RAM đang dùng {h['ram_percent']:.0f}%",
                        "Không chạy ứng dụng nặng khác khi render"))
    if h["ram_available_mb"] < s.min_free_ram_mb and q["render"]["queued"]:
        a.append(_alert("warning", "render_waiting_ram",
                        f"RAM trống {h['ram_available_mb']} MB < {s.min_free_ram_mb} MB: render tạm chờ", ""))
    if len(snap["processes"]["ffmpeg"]) > 1:
        a.append(_alert("warning", "multiple_ffmpeg", f"{len(snap['processes']['ffmpeg'])} tiến trình FFmpeg cùng chạy",
                        "Hệ thống chỉ cho phép 1 render nặng; kiểm tra tiến trình mồ côi"))
    for w in snap["workers"]:
        if w["online"]:
            continue
        busy = {"render": q["render"]["queued"], "publish": q["upload"]["queued"],
                "analytics": q["analytics"]["queued"]}.get(w["kind"], 0)
        a.append(_alert("critical" if busy else "warning", f"worker_{w['kind']}_offline",
                        f"Worker {w['kind']} không hoạt động" + (f" — {busy} tác vụ đang chờ" if busy else ""),
                        "scripts/restart.sh · journalctl -u coco-automation -n 100"))
    for st in snap["stalled"]:
        a.append(_alert("critical", f"{st['kind']}_stalled", f"Tác vụ {st['kind']} #{st['job_id']} bị treo ({st['reason']})",
                        "Watchdog sẽ dừng worker và khôi phục trong vòng 1 phút"))
    if yt["credentials"]["revoked"] or yt["credentials"]["expired"]:
        n = yt["credentials"]["revoked"] + yt["credentials"]["expired"]
        a.append(_alert("warning", "youtube_reconnect", f"{n} kênh cần kết nối lại YouTube", "Channels → tab YouTube"))
    for e in yt["sync_errors"]:
        a.append(_alert("warning", "analytics_sync_error", f"Analytics '{e['channel_name']}': {e['kind']} — {e['error']}", ""))
    if q["render"]["failed_24h"]:
        a.append(_alert("warning", "render_failures", f"{q['render']['failed_24h']} tác vụ render lỗi trong 24h", "Video Production → Jobs"))
    if q["upload"]["failed_24h"]:
        a.append(_alert("warning", "upload_failures", f"{q['upload']['failed_24h']} tác vụ upload lỗi trong 24h", "Publishing"))
    if q["render"]["oldest_queued_sec"] and q["render"]["oldest_queued_sec"] > 6 * 3600 and not q["render"]["running"]:
        a.append(_alert("warning", "render_starved", "Có tác vụ render chờ hơn 6 giờ mà không có render nào đang chạy", ""))
    if not snap["config"]["secret_key_configured"]:
        a.append(_alert("critical", "no_secret_key", "SECRET_KEY chưa cấu hình — không thể mã hóa token OAuth", "Xem .env"))
    if not snap["config"]["ffmpeg_path"]:
        a.append(_alert("warning", "no_ffmpeg", "Chưa cài FFmpeg", "sudo apt install ffmpeg"))
    a.sort(key=lambda x: -SEVERITY[x["severity"]])
    return a


def _ffmpeg_path() -> str | None:
    from app.services.overview_service import _ffmpeg_path as resolve
    return resolve()


# ---------------------------------------------------------------- public API
def snapshot(db: Session) -> dict:
    s = get_settings()
    snap = {
        "generated_at": _now(), "hostname": socket.gethostname(),
        "host": host_metrics(), "processes": process_metrics(),
        "workers": _workers(db), "queues": _queues(db),
        "youtube": _youtube(db), "database": _database(db),
        "stalled": [st.__dict__ for st in recovery.find_stalled(db)],
        "config": {"secret_key_configured": bool(s.secret_key), "ffmpeg_path": _ffmpeg_path(),
                   "dashboard_auth_enabled": bool(s.dashboard_password), "app_version": s.app_version,
                   "limits": {"min_free_disk_gb": s.min_free_disk_gb, "min_free_ram_mb": s.min_free_ram_mb,
                              "ram_warn_percent": s.ram_warn_percent, "disk_warn_gb": s.disk_warn_gb,
                              "worker_stale_seconds": s.worker_stale_seconds}},
    }
    snap["alerts"] = build_alerts(snap)
    snap["status"] = max((x["severity"] for x in snap["alerts"]), key=lambda v: SEVERITY[v], default="ok")
    return snap


def record_sample(db: Session, snap: dict | None = None) -> SystemMetric:
    snap = snap or snapshot(db)
    h, q = snap["host"], snap["queues"]
    m = SystemMetric(cpu_percent=h["cpu_percent"], ram_percent=h["ram_percent"], ram_available_mb=h["ram_available_mb"],
                     disk_free_gb=h["disk_free_gb"], ffmpeg_processes=len(snap["processes"]["ffmpeg"]),
                     ffmpeg_rss_mb=snap["processes"]["ffmpeg_rss_mb"],
                     render_queue=q["render"]["queued"] + q["render"]["running"],
                     upload_queue=q["upload"]["queued"] + q["upload"]["running"])
    db.add(m)
    db.commit()
    return m


def history(db: Session, hours: int = 6, max_points: int = 240) -> dict:
    hours = max(1, min(hours, 24 * get_settings().metrics_retention_days))
    rows = db.scalars(select(SystemMetric).where(SystemMetric.ts >= _now() - timedelta(hours=hours))
                      .order_by(SystemMetric.ts)).all()
    step = max(1, len(rows) // max_points)
    pts = [{"ts": r.ts, "cpu": r.cpu_percent, "ram": r.ram_percent, "ram_available_mb": r.ram_available_mb,
            "disk_free_gb": r.disk_free_gb, "ffmpeg": r.ffmpeg_processes, "ffmpeg_rss_mb": r.ffmpeg_rss_mb,
            "render_queue": r.render_queue, "upload_queue": r.upload_queue} for r in rows[::step]]
    return {"hours": hours, "interval_seconds": get_settings().monitor_interval_seconds, "points": pts}
