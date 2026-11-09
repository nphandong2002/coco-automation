"""Publishing worker: uploads rendered videos to YouTube.

Guarantees (mirrors the render worker)
  * ONE upload at a time (advisory lock) — friendly to an 8 GB RAM / home-bandwidth machine.
  * no duplicate publishing: a partial unique index allows one active job per video, and the
    YouTube video id is committed to the database right after upload, BEFORE thumbnail/playlist.
  * restart safe: the resumable-upload session URI is stored; after a crash the upload continues
    from the byte count YouTube reports.
  * per-channel isolation: expired tokens / quota only park THAT channel's jobs.
  * retry: exponential backoff for network/5xx; wait for quota reset; wait for reconnect on auth.
"""
from __future__ import annotations

import io
import logging
import os
import socket
import signal
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from PIL import Image
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import storage
from app.worker.util import interruptible_wait
from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.integrations.youtube.client import AUTH, PERMANENT, QUOTA, RETRYABLE, ApiError, YouTubeClient, backoff_seconds
from app.models import Channel, ContentProject, PublishingJob, Video, WorkerStatus, YoutubeCredential
from app.models.enums import CredentialStatus, JobStatus, LogLevel, PrivacyStatus, ProductionStatus, WorkerState
from app.services import activity, youtube_service
from app.services.publish_service import add_history, has_event

# Windows has no SIGTERM delivery; the supervisor sends CTRL_BREAK (SIGBREAK) for a graceful stop
_EXTRA_SIGNALS = (signal.SIGBREAK,) if hasattr(signal, "SIGBREAK") else ()
log = logging.getLogger("coco.publisher")
PUBLISH_LOCK_KEY = 72_700_002
THUMB_MAX_BYTES = 2 * 1024 * 1024


def _now() -> datetime:
    return datetime.now(timezone.utc)


def next_quota_reset(now: datetime | None = None) -> datetime:
    """YouTube Data API quota resets at midnight Pacific time."""
    now = now or _now()
    try:
        pt = ZoneInfo("America/Los_Angeles")
        local = now.astimezone(pt)
        nxt = (local + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
        return nxt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001 - tzdata missing
        return now + timedelta(hours=6)


def prepare_thumbnail(path: Path) -> tuple[bytes, str]:
    """YouTube accepts JPG/PNG up to 2 MB. Re-encode when needed (Pillow), never upscale."""
    raw = path.read_bytes()
    ext = path.suffix.lower()
    if len(raw) <= THUMB_MAX_BYTES and ext in (".jpg", ".jpeg", ".png"):
        return raw, "image/png" if ext == ".png" else "image/jpeg"
    with Image.open(io.BytesIO(raw)) as img:
        img = img.convert("RGB")
        for quality in (92, 85, 75, 65):
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=quality, optimize=True)
            if buf.tell() <= THUMB_MAX_BYTES:
                return buf.getvalue(), "image/jpeg"
        img.thumbnail((1280, 720))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=70, optimize=True)
        return buf.getvalue(), "image/jpeg"


class PublishWorker:
    def __init__(self, http: httpx.Client | None = None) -> None:
        self.settings = get_settings()
        self.http = http  # injectable for tests
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:publish"
        self.stop_event = threading.Event()
        self.lock_conn = None
        self.state = WorkerState.IDLE
        self.current_job_id: int | None = None
        self._cancelled = threading.Event()
        self._last_progress = 0.0

    # ------------------------------------------------------------- lifecycle
    def _install_signals(self) -> None:
        def _handler(signum, _frame):  # noqa: ANN001
            log.info("Signal %s received, stopping…", signum)
            self.stop_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT, *_EXTRA_SIGNALS):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                pass

    def _acquire_lock(self) -> bool:
        from sqlalchemy import text
        conn = engine.connect()
        got = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": PUBLISH_LOCK_KEY}).scalar()
        conn.commit()
        if got:
            self.lock_conn = conn
            return True
        conn.close()
        return False

    def _release_lock(self) -> None:
        from sqlalchemy import text
        if self.lock_conn is not None:
            try:
                self.lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": PUBLISH_LOCK_KEY})
                self.lock_conn.commit()
            finally:
                self.lock_conn.close()
                self.lock_conn = None

    def heartbeat(self) -> None:
        try:
            with SessionLocal() as db:
                w = db.get(WorkerStatus, self.worker_id)
                if w is None:
                    w = WorkerStatus(worker_id=self.worker_id, kind="publish", hostname=socket.gethostname(),
                                     pid=os.getpid(), started_at=_now(), info={})
                    db.add(w)
                w.state = self.state
                w.current_job_id = self.current_job_id
                w.heartbeat_at = _now()
                db.commit()
        except Exception:  # noqa: BLE001
            log.exception("heartbeat failed")

    def run(self, once: bool = False) -> int:
        self._install_signals()
        self.state = WorkerState.WAITING_LOCK
        self.heartbeat()
        while not self.stop_event.is_set():
            if self._acquire_lock():
                break
            log.warning("Another publish worker is running — waiting")
            self.heartbeat()
            interruptible_wait(self.stop_event, 10)
        if self.stop_event.is_set():
            self._shutdown()
            return 0
        log.info("Publish lock acquired (%s)", self.worker_id)
        self.recover_orphans()
        self.state = WorkerState.IDLE
        last_beat = 0.0
        try:
            while not self.stop_event.is_set():
                job_id = self.claim()
                if job_id is not None:
                    self.run_job(job_id)
                    if once:
                        break
                    continue
                if once:
                    break
                if time.monotonic() - last_beat >= self.settings.worker_heartbeat_seconds:
                    self.heartbeat()
                    last_beat = time.monotonic()
                interruptible_wait(self.stop_event, self.settings.publish_poll_seconds)
        finally:
            self._shutdown()
        return 0

    def _shutdown(self) -> None:
        self.state = WorkerState.STOPPED
        self.current_job_id = None
        self.heartbeat()
        self._release_lock()
        log.info("Publish worker stopped")

    # ------------------------------------------------------------- recovery / queue
    def recover_orphans(self) -> int:
        """Lock holder => every RUNNING job belongs to a dead worker. Resume via stored session URI."""
        n = 0
        with SessionLocal() as db:
            for job in db.scalars(select(PublishingJob).where(PublishingJob.status == JobStatus.RUNNING)).all():
                n += 1
                if job.attempts < job.max_attempts:
                    job.status = JobStatus.QUEUED
                    add_history(job, "recovered", "worker dừng đột ngột, sẽ tiếp tục upload")
                    msg, level = f"Khôi phục tác vụ đăng #{job.id} sau khi worker dừng", LogLevel.WARNING
                else:
                    job.status = JobStatus.FAILED
                    job.last_error = "Worker dừng đột ngột nhiều lần khi đang upload"
                    add_history(job, "failed", job.last_error)
                    msg, level = f"Tác vụ đăng #{job.id} thất bại sau khi worker dừng", LogLevel.ERROR
                activity.record(db, "publishing", msg, channel_id=job.channel_id, level=level)
            db.commit()
        if n:
            log.warning("Recovered %d orphaned publishing job(s)", n)
        return n

    def claim(self) -> int | None:
        now = _now()
        with SessionLocal() as db:
            job = db.scalar(
                select(PublishingJob)
                .join(Channel, Channel.id == PublishingJob.channel_id)
                .join(YoutubeCredential, YoutubeCredential.channel_id == PublishingJob.channel_id)
                .where(PublishingJob.status == JobStatus.QUEUED, Channel.enabled.is_(True),
                       YoutubeCredential.status == CredentialStatus.VALID,
                       or_(PublishingJob.next_attempt_at.is_(None), PublishingJob.next_attempt_at <= now))
                .order_by(PublishingJob.next_attempt_at.nulls_first(), PublishingJob.created_at, PublishingJob.id)
                .with_for_update(skip_locked=True, of=PublishingJob)
                .limit(1)
            )
            if job is None:
                return None
            job.status = JobStatus.RUNNING
            job.attempts += 1
            job.next_attempt_at = None
            add_history(job, "started", f"lần {job.attempts}/{job.max_attempts}")
            db.commit()
            return job.id

    # ------------------------------------------------------------- execution
    def _should_stop(self) -> bool:
        return self.stop_event.is_set() or self._cancelled.is_set()

    def _on_progress(self, job_id: int, sent: int, total: int) -> None:
        now = time.monotonic()
        if now - self._last_progress < 2.0 and sent < total:
            return
        self._last_progress = now
        self.heartbeat()  # a multi-hour upload must not look like a dead worker
        try:
            with SessionLocal() as db:
                job = db.get(PublishingJob, job_id)
                if job is None or job.status != JobStatus.RUNNING:
                    self._cancelled.set()  # cancelled by the user
                    return
                job.bytes_uploaded = sent
                db.commit()
        except Exception:  # noqa: BLE001
            log.exception("progress update failed")

    def run_job(self, job_id: int) -> None:
        self.current_job_id = job_id
        self.state = WorkerState.UPLOADING
        self._cancelled.clear()
        self.heartbeat()
        client: YouTubeClient | None = None
        try:
            with SessionLocal() as db:
                job = db.get(PublishingJob, job_id)
                channel_id = job.channel_id
            client = youtube_service.client_for(channel_id, self.http)
            self._execute(job_id, client)
        except ApiError as exc:
            self._handle_error(job_id, exc)
        except Exception as exc:  # noqa: BLE001 - never let one job kill the worker
            log.exception("Publishing job #%s crashed", job_id)
            self._handle_error(job_id, ApiError(f"Lỗi nội bộ: {exc.__class__.__name__}: {exc}", RETRYABLE))
        finally:
            if client is not None:
                client.close()
            self.current_job_id = None
            self.state = WorkerState.IDLE
            self.heartbeat()

    def _execute(self, job_id: int, client: YouTubeClient) -> None:
        with SessionLocal() as db:
            job = db.get(PublishingJob, job_id)
            video = db.get(Video, job.video_id)
            if video is None:
                raise ApiError("Video không còn tồn tại", PERMANENT)
            try:
                video_path = storage.resolve(video.file_path)
            except storage.StorageError as exc:
                raise ApiError(str(exc), PERMANENT) from exc
            if not video_path.is_file():
                raise ApiError("File video không còn trên đĩa", PERMANENT)
            thumb_rel = video.thumbnail_path
            uploaded_id = job.youtube_video_id
            snapshot = dict(title=job.title, description=job.description, tags=list(job.tags or []),
                            category_id=job.category_id, privacy=job.privacy_status.value,
                            publish_at=job.publish_at, uri=job.upload_session_uri, playlist_id=job.playlist_id)

        # ---- 1) upload (skipped if a previous attempt already created the YouTube video)
        if not uploaded_id:
            uploaded_id = self._upload(job_id, client, video_path, snapshot)
        # ---- 2) post-upload steps; each is idempotent via history markers
        warnings: list[str] = []
        self._post_step(job_id, "thumbnail", warnings,
                        lambda: self._set_thumbnail(client, uploaded_id, thumb_rel) if thumb_rel else None,
                        skip_if_missing=thumb_rel is None)
        if snapshot["playlist_id"]:
            self._post_step(job_id, "playlist", warnings,
                            lambda: client.add_to_playlist(snapshot["playlist_id"], uploaded_id))
        self._finish_success(job_id, uploaded_id, warnings)

    def _upload(self, job_id: int, client: YouTubeClient, path: Path, snap: dict) -> str:
        size = path.stat().st_size
        publish_iso = snap["publish_at"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z") \
            if snap["publish_at"] else None
        uri = snap["uri"]
        resume = bool(uri)
        if not uri:
            meta = client.build_metadata(title=snap["title"], description=snap["description"], tags=snap["tags"],
                                         category_id=snap["category_id"], privacy=snap["privacy"],
                                         publish_at_iso=publish_iso)
            uri = client.start_upload(meta, size)
            with SessionLocal() as db:
                job = db.get(PublishingJob, job_id)
                job.upload_session_uri = uri
                job.bytes_uploaded = 0
                add_history(job, "session_started", f"{size / 1024**2:.0f} MB")
                db.commit()
        try:
            result = client.upload_file(uri, path, resume=resume,
                                        on_progress=lambda s, t: self._on_progress(job_id, s, t),
                                        should_stop=self._should_stop)
        except ApiError as exc:
            if exc.reason == "sessionExpired":
                with SessionLocal() as db:
                    job = db.get(PublishingJob, job_id)
                    job.upload_session_uri = None
                    job.bytes_uploaded = 0
                    db.commit()
            raise
        yt_id = result.get("id")
        if not yt_id:
            raise ApiError("YouTube không trả id video", RETRYABLE)
        # Commit the YouTube id IMMEDIATELY: a crash after this point can never re-upload the video.
        with SessionLocal() as db:
            job = db.get(PublishingJob, job_id)
            video = db.get(Video, job.video_id)
            job.youtube_video_id = yt_id
            job.uploaded_at = _now()
            job.bytes_uploaded = size
            job.upload_session_uri = None
            video.youtube_video_id = yt_id
            video.privacy_status = job.privacy_status
            video.published_at = job.publish_at or (_now() if job.privacy_status == PrivacyStatus.PUBLIC else None)
            if video.content_project_id:
                p = db.get(ContentProject, video.content_project_id)
                if p is not None:
                    p.status = ProductionStatus.PUBLISHED
            add_history(job, "uploaded", yt_id)
            activity.record(db, "publishing", f"Đã upload '{job.title}' lên YouTube ({job.privacy_status.value})",
                            channel_id=job.channel_id, details={"youtube_video_id": yt_id})
            db.commit()
        return yt_id

    def _set_thumbnail(self, client: YouTubeClient, yt_id: str, thumb_rel: str) -> None:
        path = storage.resolve(thumb_rel)
        if not path.is_file():
            raise ApiError("File thumbnail không còn trên đĩa", PERMANENT)
        data, mime = prepare_thumbnail(path)
        client.set_thumbnail(yt_id, data, mime)

    def _post_step(self, job_id: int, name: str, warnings: list[str], fn, skip_if_missing: bool = False) -> None:  # noqa: ANN001
        with SessionLocal() as db:
            if has_event(db.get(PublishingJob, job_id), f"{name}_done"):
                return
        if skip_if_missing:
            return
        try:
            fn()
            event, detail = f"{name}_done", ""
        except ApiError as exc:
            if exc.kind != PERMANENT:
                raise  # retried later: the video is already uploaded, only this step re-runs
            # e.g. thumbnails need a verified channel; do not fail an already-published video
            event, detail = f"{name}_done", f"bỏ qua: {exc}"
            warnings.append(f"{name}: {exc}")
        with SessionLocal() as db:
            job = db.get(PublishingJob, job_id)
            add_history(job, event, detail)
            db.commit()

    def _finish_success(self, job_id: int, yt_id: str, warnings: list[str]) -> None:
        with SessionLocal() as db:
            job = db.get(PublishingJob, job_id)
            if job.status != JobStatus.RUNNING:
                return  # cancelled while finishing: leave the record as the user left it
            job.status = JobStatus.SUCCEEDED
            job.last_error = "; ".join(warnings)[:1000] if warnings else None
            job.next_attempt_at = None
            add_history(job, "succeeded", yt_id)
            ch = db.get(Channel, job.channel_id)
            if ch is not None and ch.last_error and ch.last_error.startswith("Đăng YouTube"):
                ch.last_error = None
                ch.last_error_at = None
            db.commit()
        log.info("Publishing job #%s succeeded (%s)", job_id, yt_id)

    # ------------------------------------------------------------- errors
    def _handle_error(self, job_id: int, exc: ApiError) -> None:
        log.warning("Publishing job #%s: %s (%s)", job_id, exc, exc.kind)
        with SessionLocal() as db:
            job = db.get(PublishingJob, job_id)
            if job is None or job.status == JobStatus.CANCELLED:
                return
            msg = str(exc)[:2000]
            job.last_error = msg
            if exc.reason == "stopped":
                job.status = JobStatus.QUEUED  # worker shutting down: not an attempt
                job.attempts = max(0, job.attempts - 1)
                add_history(job, "paused", "worker dừng, sẽ tiếp tục khi khởi động lại")
            elif exc.kind == AUTH:
                job.status = JobStatus.QUEUED  # parked until the channel is reconnected
                job.attempts = max(0, job.attempts - 1)
                add_history(job, "auth_error", msg)
                db.commit()
                cred = db.scalar(select(YoutubeCredential).where(YoutubeCredential.channel_id == job.channel_id))
                if cred is not None and cred.status == CredentialStatus.VALID:
                    youtube_service.mark_revoked(job.channel_id, msg)
                return
            elif exc.kind == QUOTA:
                job.status = JobStatus.QUEUED
                job.attempts = max(0, job.attempts - 1)
                job.next_attempt_at = next_quota_reset()
                add_history(job, "quota", f"hết quota API, thử lại sau {job.next_attempt_at.isoformat(timespec='minutes')}")
                activity.record(db, "publishing", "Hết quota YouTube API, tạm hoãn các tác vụ đăng",
                                channel_id=job.channel_id, level=LogLevel.WARNING)
            elif exc.kind == RETRYABLE and job.attempts < job.max_attempts:
                delay = backoff_seconds(job.attempts)
                job.status = JobStatus.QUEUED
                job.next_attempt_at = _now() + timedelta(seconds=delay)
                add_history(job, "retry_scheduled", f"{msg[:200]} — thử lại sau {delay}s")
                activity.record(db, "publishing", f"Upload lỗi, thử lại sau {delay}s: {msg[:150]}",
                                channel_id=job.channel_id, level=LogLevel.WARNING)
            else:
                job.status = JobStatus.FAILED
                add_history(job, "failed", msg)
                ch = db.get(Channel, job.channel_id)
                if ch is not None:  # only THIS channel is flagged
                    ch.last_error = f"Đăng YouTube thất bại (tác vụ #{job.id}): {msg[:300]}"
                    ch.last_error_at = _now()
                activity.record(db, "publishing", f"Đăng video thất bại #{job.id}: {msg[:200]}",
                                channel_id=job.channel_id, level=LogLevel.ERROR)
            db.commit()
