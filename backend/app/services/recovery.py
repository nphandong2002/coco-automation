"""Self-healing: hung-job watchdog, orphan FFmpeg cleanup and routine maintenance.

The workers already recover from a crash when they START (they hold an advisory lock, so every RUNNING
job in the database belongs to a dead worker). What was missing is a worker that is ALIVE BUT HUNG: a render
that stopped heartbeating, an upload stuck on a dead socket, a sync that never returns. The watchdog finds
such jobs from database evidence only, terminates the owning worker process (SIGTERM, then SIGKILL) and lets
the supervisor in scripts/run.sh restart it — start-up recovery then re-queues or fails the job.
"""
from __future__ import annotations

import logging
import os
import shutil
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import psutil
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core import storage
from app.core.config import get_settings
from app.models import PublishingJob, SchedulerJob, SystemLog, SystemMetric, VideoJob, WorkerStatus
from app.models.enums import JobStatus, LogLevel, WorkerState
from app.services import activity
from app.services.analytics_sync import JOB_TYPE as ANALYTICS_JOB

log = logging.getLogger("coco.recovery")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Stalled:
    kind: str                 # render | publish | analytics
    job_id: int
    channel_id: int | None
    age_sec: int
    reason: str


# ---------------------------------------------------------------- detection
def find_stalled(db: Session, now: datetime | None = None) -> list[Stalled]:
    s = get_settings()
    now = now or _now()
    out: list[Stalled] = []

    for j in db.scalars(select(VideoJob).where(VideoJob.status == JobStatus.RUNNING)).all():
        last = j.heartbeat_at or j.started_at
        if last is None:
            continue
        idle = (now - last).total_seconds()
        runtime = (now - j.started_at).total_seconds() if j.started_at else 0
        if idle > s.worker_stale_seconds:
            out.append(Stalled("render", j.id, j.channel_id, int(idle), f"không có heartbeat {int(idle)}s"))
        elif j.timeout_sec and runtime > j.timeout_sec + 300:
            out.append(Stalled("render", j.id, j.channel_id, int(runtime), f"vượt timeout {j.timeout_sec}s"))

    for p in db.scalars(select(PublishingJob).where(PublishingJob.status == JobStatus.RUNNING)).all():
        idle = (now - p.updated_at).total_seconds()  # updated_at moves on every progress write
        if idle > s.publish_stall_seconds:
            out.append(Stalled("publish", p.id, p.channel_id, int(idle), f"upload không tiến triển {int(idle)}s"))

    for a in db.scalars(select(SchedulerJob).where(SchedulerJob.job_type == ANALYTICS_JOB,
                                                   SchedulerJob.status == JobStatus.RUNNING)).all():
        if a.locked_at is not None and (now - a.locked_at).total_seconds() > (a.timeout_sec or 1800):
            out.append(Stalled("analytics", a.id, a.channel_id, int((now - a.locked_at).total_seconds()),
                               "đồng bộ vượt timeout"))
    return out


# ---------------------------------------------------------------- process control
def _is_worker_process(pid: int) -> bool:
    try:
        cmd = " ".join(psutil.Process(pid).cmdline())
    except (psutil.Error, OSError):
        return False
    return "app.worker" in cmd


def terminate_tree(pid: int, grace: float) -> bool:
    """SIGTERM the process and its children, SIGKILL whatever survives `grace` seconds. Returns True if it was alive."""
    try:
        proc = psutil.Process(pid)
        procs = [proc, *proc.children(recursive=True)]
    except (psutil.Error, OSError):
        return False
    for p in procs:
        try:
            p.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(procs, timeout=grace)
    for p in alive:
        try:
            p.kill()
        except psutil.Error:
            pass
    return True


def _owner(db: Session, st: Stalled) -> WorkerStatus | None:
    return db.scalar(select(WorkerStatus).where(WorkerStatus.kind == st.kind, WorkerStatus.current_job_id == st.job_id,
                                                WorkerStatus.state != WorkerState.STOPPED))


def watchdog(db: Session) -> list[str]:
    """Terminate workers that hold a hung job. Returns human-readable actions taken."""
    s = get_settings()
    actions: list[str] = []
    for st in find_stalled(db):
        w = _owner(db, st)
        if w is None:
            actions.append(f"{st.kind} #{st.job_id}: treo ({st.reason}) nhưng không thấy worker sở hữu — chờ worker khởi động lại để khôi phục")
            continue
        if w.hostname != socket.gethostname() or not _is_worker_process(w.pid):
            # worker row is stale: its process is already gone, a restart will recover the job
            w.state = WorkerState.STOPPED
            actions.append(f"{st.kind} #{st.job_id}: worker {w.worker_id} đã chết")
        else:
            killed = terminate_tree(w.pid, s.watchdog_kill_grace_seconds)
            w.state = WorkerState.STOPPED
            actions.append(f"{st.kind} #{st.job_id}: {st.reason} → đã dừng worker PID {w.pid} ({'đã kill' if killed else 'đã thoát'})")
        activity.record(db, "watchdog", f"Tác vụ {st.kind} #{st.job_id} bị treo ({st.reason}); đã dừng worker để khôi phục",
                        channel_id=st.channel_id, level=LogLevel.ERROR,
                        details={"kind": st.kind, "job_id": st.job_id, "age_sec": st.age_sec})
        db.commit()
    return actions


def kill_orphan_ffmpeg() -> int:
    """FFmpeg processes of OUR storage whose parent worker is gone (re-parented to init) keep eating CPU/RAM."""
    root = str(storage.storage_root())
    n = 0
    for p in psutil.process_iter(["pid", "name", "ppid", "cmdline"]):
        try:
            name = (p.info["name"] or "").lower()
            if not name.startswith("ffmpeg") or not any(root in a for a in (p.info["cmdline"] or [])):
                continue
            parent = psutil.Process(p.info["ppid"]) if p.info["ppid"] else None
            alive_parent = parent is not None and p.info["ppid"] > 1 and parent.is_running()
            if not alive_parent:
                terminate_tree(p.info["pid"], 5)
                n += 1
        except (psutil.Error, OSError):
            continue
    if n:
        log.warning("Killed %d orphan ffmpeg process(es)", n)
    return n


# ---------------------------------------------------------------- maintenance
def _prune_tmp(max_age_hours: int) -> tuple[int, int]:
    """Remove stale files under storage/tmp. Skipped entirely while a render is running."""
    tmp = storage.tmp_dir()
    removed = freed = 0
    if not tmp.exists():
        return 0, 0
    cutoff = time.time() - max_age_hours * 3600
    for path in sorted(tmp.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                size = path.stat().st_size
                path.unlink()
                removed += 1
                freed += size
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        except OSError:
            continue
    return removed, freed


def maintenance(db: Session) -> dict:
    """Idempotent housekeeping, safe to run any time."""
    s = get_settings()
    now = _now()
    report: dict = {}
    r = db.execute(delete(SystemLog).where(SystemLog.created_at < now - timedelta(days=s.log_retention_days)))
    report["system_logs_deleted"] = r.rowcount
    r = db.execute(delete(SystemMetric).where(SystemMetric.ts < now - timedelta(days=s.metrics_retention_days)))
    report["metrics_deleted"] = r.rowcount
    r = db.execute(delete(WorkerStatus).where(WorkerStatus.heartbeat_at < now - timedelta(days=1),
                                              WorkerStatus.state == WorkerState.STOPPED))
    report["worker_rows_deleted"] = r.rowcount
    r = db.execute(delete(SchedulerJob).where(SchedulerJob.status.in_([JobStatus.SUCCEEDED, JobStatus.FAILED,
                                                                       JobStatus.CANCELLED]),
                                              SchedulerJob.finished_at < now - timedelta(days=30)))
    report["scheduler_jobs_deleted"] = r.rowcount
    running_render = db.scalar(select(func.count()).select_from(VideoJob).where(VideoJob.status == JobStatus.RUNNING))
    if running_render:
        report["tmp_files_deleted"], report["tmp_bytes_freed"] = 0, 0
        report["tmp_skipped"] = "đang có tác vụ render"
    else:
        report["tmp_files_deleted"], report["tmp_bytes_freed"] = _prune_tmp(s.tmp_max_age_hours)
    db.commit()
    report["orphan_ffmpeg_killed"] = kill_orphan_ffmpeg()
    return report


def sample_pid_alive(pid: int) -> bool:  # tiny helper for tests/monitoring
    return psutil.pid_exists(pid) and pid != os.getpid()
