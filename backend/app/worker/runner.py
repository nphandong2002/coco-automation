"""Render worker.

Guarantees
  * ONE heavy render at a time on the machine: the worker holds a PostgreSQL advisory lock for
    its whole life; a second worker process waits instead of rendering in parallel.
  * no duplicate work: jobs are claimed with SELECT … FOR UPDATE SKIP LOCKED and a partial
    unique index forbids two active jobs for one project.
  * crash / restart safe: the queue lives in PostgreSQL. On start-up the lock holder re-queues
    jobs left RUNNING by a dead worker (or fails them when attempts are exhausted).
  * graceful stop (SIGTERM): the running FFmpeg is stopped and the job goes back to the queue.
  * channel isolation: jobs of paused channels wait; a failing job only marks ITS channel as Error.
"""
from __future__ import annotations

import logging
import os
import shutil
import signal
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core import storage
from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.models import Channel, ContentProject, Video, VideoJob, WorkerStatus
from app.models.enums import JobStatus, LogLevel, ProductionStatus, VideoJobType, WorkerState
from app.render import ffmpeg as ff
from app.render.pipeline import RenderFailed, render
from app.render.video import estimate_size_bytes
from app.services import activity, render_service

log = logging.getLogger("coco.worker")

RENDER_LOCK_KEY = 72_700_001
RETRYABLE = (ff.FFmpegError, OSError)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RenderWorker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self.stop_event = threading.Event()
        self.lock_conn = None
        self.state = WorkerState.IDLE
        self.current_job_id: int | None = None
        self._cancel_flag = threading.Event()
        self._last_progress_write = 0.0

    # ------------------------------------------------------------- lifecycle
    def _install_signals(self) -> None:
        def _handler(signum, _frame):  # noqa: ANN001
            log.info("Signal %s received, stopping…", signum)
            self.stop_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):  # not in main thread / unsupported
                pass

    def _acquire_lock(self) -> bool:
        conn = engine.connect()
        got = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": RENDER_LOCK_KEY}).scalar()
        conn.commit()
        if got:
            self.lock_conn = conn
            return True
        conn.close()
        return False

    def _release_lock(self) -> None:
        if self.lock_conn is not None:
            try:
                self.lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": RENDER_LOCK_KEY})
                self.lock_conn.commit()
            finally:
                self.lock_conn.close()
                self.lock_conn = None

    def heartbeat(self, info: dict | None = None) -> None:
        try:
            with SessionLocal() as db:
                w = db.get(WorkerStatus, self.worker_id)
                if w is None:
                    version = None
                    try:
                        version = ff.ffmpeg_version()[2]
                    except Exception:  # noqa: BLE001
                        pass
                    w = WorkerStatus(worker_id=self.worker_id, kind="render", hostname=socket.gethostname(),
                                     pid=os.getpid(), started_at=_now(),
                                     info={"ffmpeg": version, "threads": ff.render_threads()})
                    db.add(w)
                w.state = self.state
                w.current_job_id = self.current_job_id
                w.heartbeat_at = _now()
                if info:
                    w.info = {**(w.info or {}), **info}
                db.commit()
        except Exception:  # noqa: BLE001 - heartbeat must never kill the worker
            log.exception("heartbeat failed")

    def run(self, once: bool = False) -> int:
        self._install_signals()
        self.state = WorkerState.WAITING_LOCK
        self.heartbeat()
        while not self.stop_event.is_set():
            if self._acquire_lock():
                break
            log.warning("Another render worker holds the render lock — waiting (only one heavy render at a time)")
            self.heartbeat()
            self.stop_event.wait(10)
        if self.stop_event.is_set():
            self._shutdown()
            return 0
        log.info("Render lock acquired (%s)", self.worker_id)
        self.recover_orphans()
        self.state = WorkerState.IDLE
        processed = 0
        last_beat = 0.0
        try:
            while not self.stop_event.is_set():
                job_id = self.claim()
                if job_id is not None:
                    self.run_job(job_id)
                    processed += 1
                    if once:
                        break
                    continue
                if once:
                    break
                if time.monotonic() - last_beat >= self.settings.worker_heartbeat_seconds:
                    self.heartbeat()
                    last_beat = time.monotonic()
                self.stop_event.wait(self.settings.worker_poll_seconds)
        finally:
            self._shutdown()
        return 0

    def _shutdown(self) -> None:
        self.state = WorkerState.STOPPED
        self.current_job_id = None
        self.heartbeat()
        self._release_lock()
        log.info("Render worker stopped")

    # ------------------------------------------------------------- recovery
    def recover_orphans(self) -> int:
        """Called while holding the render lock: every RUNNING job belongs to a dead worker."""
        n = 0
        with SessionLocal() as db:
            for job in db.scalars(select(VideoJob).where(VideoJob.status == JobStatus.RUNNING)).all():
                n += 1
                if job.attempts < job.max_attempts:
                    job.status = JobStatus.QUEUED
                    job.step = "Khôi phục: worker đã dừng đột ngột, chạy lại"
                    job.worker_id = None
                    job.cancel_requested = False
                    msg = f"Khôi phục tác vụ render #{job.id} sau khi worker dừng"
                    self._set_project_status(db, job, ProductionStatus.QUEUED)
                    level = LogLevel.WARNING
                else:
                    self._fail(db, job, "Worker dừng đột ngột nhiều lần khi đang render", commit=False)
                    msg = f"Tác vụ render #{job.id} thất bại sau khi worker dừng"
                    level = LogLevel.ERROR
                activity.record(db, "render", msg, channel_id=job.channel_id, level=level)
            db.commit()
        jobs_tmp = storage.tmp_dir() / "jobs"
        if jobs_tmp.exists():
            shutil.rmtree(jobs_tmp, ignore_errors=True)
        if n:
            log.warning("Recovered %d orphaned job(s)", n)
        return n

    # ------------------------------------------------------------- queue
    def claim(self) -> int | None:
        with SessionLocal() as db:
            job = db.scalar(
                select(VideoJob)
                .join(Channel, Channel.id == VideoJob.channel_id)
                .where(VideoJob.status == JobStatus.QUEUED, Channel.enabled.is_(True))
                .order_by(VideoJob.priority, VideoJob.created_at, VideoJob.id)
                .with_for_update(skip_locked=True, of=VideoJob)
                .limit(1)
            )
            if job is None:
                return None
            job.status = JobStatus.RUNNING
            job.worker_id = self.worker_id
            job.attempts += 1
            job.started_at = job.heartbeat_at = _now()
            job.progress = 0.0
            job.step = "Bắt đầu"
            job.error = None
            job.cancel_requested = False
            self._set_project_status(db, job, ProductionStatus.RENDERING)
            db.commit()
            return job.id

    @staticmethod
    def _set_project_status(db: Session, job: VideoJob, status: ProductionStatus) -> None:
        if job.job_type != VideoJobType.FULL:
            return
        db.execute(update(ContentProject).where(ContentProject.id == job.content_project_id)
                   .values(status=status))

    # ------------------------------------------------------------- job execution
    def _job_heartbeat_loop(self, job_id: int, done: threading.Event) -> None:
        while not done.wait(self.settings.worker_heartbeat_seconds):
            try:
                with SessionLocal() as db:
                    job = db.get(VideoJob, job_id)
                    if job is None or job.cancel_requested:
                        self._cancel_flag.set()
                    if job is not None:
                        job.heartbeat_at = _now()
                        db.commit()
            except Exception:  # noqa: BLE001
                log.exception("job heartbeat failed")
            self.heartbeat()

    def _progress(self, job_id: int, frac: float, step: str) -> None:
        now = time.monotonic()
        if now - self._last_progress_write < 2.0 and frac < 0.999:
            return
        self._last_progress_write = now
        labels = {"prepare": "Chuẩn bị hình ảnh", "base": "Render vòng lặp hình ảnh", "audio": "Mix âm thanh",
                  "final": "Ghép video", "thumbnail": "Tạo thumbnail", "qc": "Kiểm tra chất lượng"}
        try:
            with SessionLocal() as db:
                db.execute(update(VideoJob).where(VideoJob.id == job_id)
                           .values(progress=round(frac, 4), step=labels.get(step, step), heartbeat_at=_now()))
                db.commit()
        except Exception:  # noqa: BLE001
            log.exception("progress update failed")

    def _should_cancel(self) -> bool:
        return self._cancel_flag.is_set() or self.stop_event.is_set()

    def run_job(self, job_id: int) -> None:
        with SessionLocal() as db:
            job = db.get(VideoJob, job_id)
            plan = dict(job.render_config)
            channel_id = job.channel_id
            job_type = job.job_type
            timeout = job.timeout_sec or render_service.job_timeout(job.duration_sec or 3600)
            out_rel = render_service.output_dir_for(job)
            log_rel = Path("channels") / str(channel_id) / "jobs" / str(job_id) / "render.log"
            job.log_path = log_rel.as_posix()
            db.commit()

        self.current_job_id = job_id
        self.state = WorkerState.RENDERING
        self._cancel_flag.clear()
        self.heartbeat()
        workdir = storage.tmp_dir() / "jobs" / str(job_id)
        out_dir = storage.storage_root() / out_rel
        log_file = storage.storage_root() / log_rel
        done = threading.Event()
        hb = threading.Thread(target=self._job_heartbeat_loop, args=(job_id, done), daemon=True)
        hb.start()
        log.info("Rendering job #%s (%s, %.0fs)", job_id, job_type.value, plan.get("duration_sec", 0))
        try:
            self._check_disk(plan)
            result = render(plan, resolve=storage.resolve, workdir=workdir, output_dir=out_dir, log_file=log_file,
                            on_progress=lambda f, s: self._progress(job_id, f, s),
                            should_cancel=self._should_cancel, timeout=float(timeout))
            self._finish_success(job_id, plan, result, out_rel)
        except ff.RenderCancelled:
            self._finish_cancelled(job_id, shutdown=self.stop_event.is_set() and not self._cancel_flag.is_set())
            shutil.rmtree(out_dir, ignore_errors=True)
        except Exception as exc:  # noqa: BLE001 - every failure is recorded on the job
            log.exception("Job #%s failed", job_id)
            retry = isinstance(exc, RETRYABLE) and not isinstance(exc, (RenderFailed, ff.RenderTimeout))
            qc = exc.qc if isinstance(exc, RenderFailed) else None
            self._finish_failed(job_id, str(exc) or exc.__class__.__name__, retry, qc)
            shutil.rmtree(out_dir, ignore_errors=True)
        finally:
            done.set()
            hb.join(timeout=5)
            shutil.rmtree(workdir, ignore_errors=True)
            self.current_job_id = None
            self.state = WorkerState.IDLE
            self.heartbeat()

    def _check_disk(self, plan: dict) -> None:
        need = estimate_size_bytes(plan["duration_sec"], plan["video"]["max_bitrate_kbps"],
                                   plan["audio"]["bitrate_kbps"]) * 2  # temp file + final
        need += int(self.settings.min_free_disk_gb * 1024**3)
        free = shutil.disk_usage(storage.storage_root()).free
        if free < need:
            raise RenderFailed(f"Không đủ dung lượng đĩa: cần ~{need / 1024**3:.1f} GB, còn {free / 1024**3:.1f} GB")

    def _finish_success(self, job_id: int, plan: dict, result, out_rel: Path) -> None:  # noqa: ANN001
        root = storage.storage_root()
        with SessionLocal() as db:
            job = db.get(VideoJob, job_id)
            p = db.get(ContentProject, job.content_project_id)
            rel_video = result.video_path.relative_to(root).as_posix()
            rel_thumb = result.thumbnail_path.relative_to(root).as_posix() if result.thumbnail_path else None
            job.status = JobStatus.SUCCEEDED
            job.progress = 1.0
            job.step = "Hoàn tất"
            job.finished_at = _now()
            job.output_path = rel_video
            job.error = None
            if job.job_type == VideoJobType.FULL:
                video = Video(channel_id=job.channel_id, content_project_id=job.content_project_id,
                              video_job_id=job.id, title=plan.get("title") or (p.title if p else "Video"),
                              file_path=rel_video, duration_sec=result.duration, width=result.width,
                              height=result.height, fps=result.fps, size_bytes=result.size_bytes,
                              sha256=result.sha256, thumbnail_path=rel_thumb,
                              qc_report={k: v for k, v in result.qc.items() if k != "info"} |
                              {"info": result.qc.get("info"), "plan_fingerprint": plan.get("fingerprint")})
                db.add(video)
                if p is not None:
                    p.status = ProductionStatus.RENDERED
                    p.last_error = None
                    if not p.thumbnail_path and rel_thumb:
                        p.thumbnail_path = rel_thumb
                ch = db.get(Channel, job.channel_id)
                if ch is not None and ch.last_error and ch.last_error.startswith("Render"):
                    ch.last_error = None
                    ch.last_error_at = None
                msg = f"Render xong video '{plan.get('title')}' ({result.size_bytes / 1024**2:.0f} MB)"
            else:
                render_service.cleanup_old_previews(db, job.content_project_id)
                msg = f"Render xong bản xem thử '{plan.get('title')}'"
            activity.record(db, "render", msg, channel_id=job.channel_id, details={"job_id": job.id})
            db.commit()
        log.info("Job #%s succeeded", job_id)

    def _finish_cancelled(self, job_id: int, shutdown: bool) -> None:
        with SessionLocal() as db:
            job = db.get(VideoJob, job_id)
            if shutdown:
                # worker is stopping (restart/shutdown): put the job back, don't count the attempt
                job.status = JobStatus.QUEUED
                job.attempts = max(0, job.attempts - 1)
                job.step = "Worker dừng — sẽ render lại khi khởi động"
                job.progress = 0.0
                self._set_project_status(db, job, ProductionStatus.QUEUED)
                msg = f"Tác vụ render #{job.id} được đưa lại hàng đợi (worker dừng)"
            else:
                job.status = JobStatus.CANCELLED
                job.step = "Đã hủy"
                job.finished_at = _now()
                self._set_project_status(db, job, ProductionStatus.READY)
                msg = f"Đã hủy tác vụ render #{job.id}"
            activity.record(db, "render", msg, channel_id=job.channel_id, level=LogLevel.WARNING)
            db.commit()

    def _fail(self, db: Session, job: VideoJob, error: str, commit: bool = True, qc: dict | None = None) -> None:
        job.status = JobStatus.FAILED
        job.error = error[:4000]
        job.step = "Thất bại"
        job.finished_at = _now()
        if job.job_type == VideoJobType.FULL:
            p = db.get(ContentProject, job.content_project_id)
            if p is not None:
                p.status = ProductionStatus.FAILED
                p.last_error = error[:2000]
            # only THIS channel is flagged; other channels keep working
            ch = db.get(Channel, job.channel_id)
            if ch is not None:
                ch.last_error = f"Render thất bại (tác vụ #{job.id}): {error[:300]}"
                ch.last_error_at = _now()
        activity.record(db, "render", f"Render thất bại tác vụ #{job.id}: {error[:200]}", channel_id=job.channel_id,
                        level=LogLevel.ERROR, details={"job_id": job.id, "qc": qc} if qc else {"job_id": job.id})
        if commit:
            db.commit()

    def _finish_failed(self, job_id: int, error: str, retry: bool, qc: dict | None) -> None:
        with SessionLocal() as db:
            job = db.get(VideoJob, job_id)
            if retry and job.attempts < job.max_attempts and not self.stop_event.is_set():
                job.status = JobStatus.QUEUED
                job.error = error[:4000]
                job.step = f"Lỗi, sẽ thử lại ({job.attempts}/{job.max_attempts})"
                job.progress = 0.0
                self._set_project_status(db, job, ProductionStatus.QUEUED)
                activity.record(db, "render", f"Render tác vụ #{job.id} lỗi, thử lại: {error[:150]}",
                                channel_id=job.channel_id, level=LogLevel.WARNING)
                db.commit()
            else:
                self._fail(db, job, error, qc=qc)
