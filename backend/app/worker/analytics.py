"""Analytics worker: keeps YouTube metrics in sync for every connected channel.

  * one worker only (advisory lock) and one channel at a time — light on RAM and API quota.
  * automatic schedule (`ANALYTICS_SYNC_INTERVAL_MINUTES`) + on-demand jobs from the dashboard,
    both through the persistent `scheduler_jobs` queue (survives restarts, no duplicate jobs).
  * a channel that fails (revoked token, quota, missing scope) only parks ITSELF.
"""
from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

from app.worker.util import interruptible_wait
from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.models import WorkerStatus
from app.models.enums import WorkerState
from app.services import analytics_sync

# Windows has no SIGTERM delivery; the supervisor sends CTRL_BREAK (SIGBREAK) for a graceful stop
_EXTRA_SIGNALS = (signal.SIGBREAK,) if hasattr(signal, "SIGBREAK") else ()
log = logging.getLogger("coco.analytics.worker")
ANALYTICS_LOCK_KEY = 72_700_003


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AnalyticsWorker:
    def __init__(self, http: httpx.Client | None = None) -> None:
        self.settings = get_settings()
        self.http = http  # injectable for tests
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:analytics"
        self.stop_event = threading.Event()
        self.lock_conn = None
        self.state = WorkerState.IDLE
        self.current_job_id: int | None = None

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
        conn = engine.connect()
        got = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": ANALYTICS_LOCK_KEY}).scalar()
        conn.commit()
        if got:
            self.lock_conn = conn
            return True
        conn.close()
        return False

    def _release_lock(self) -> None:
        if self.lock_conn is not None:
            try:
                self.lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ANALYTICS_LOCK_KEY})
                self.lock_conn.commit()
            finally:
                self.lock_conn.close()
                self.lock_conn = None

    def heartbeat(self) -> None:
        try:
            with SessionLocal() as db:
                w = db.get(WorkerStatus, self.worker_id)
                if w is None:
                    w = WorkerStatus(worker_id=self.worker_id, kind="analytics", hostname=socket.gethostname(),
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
            log.warning("Another analytics worker is running — waiting")
            self.heartbeat()
            interruptible_wait(self.stop_event, 10)
        if self.stop_event.is_set():
            self._shutdown()
            return 0
        log.info("Analytics lock acquired (%s)", self.worker_id)
        n = analytics_sync.recover_running_jobs()
        if n:
            log.warning("Re-queued %d interrupted analytics job(s)", n)
        self.state = WorkerState.IDLE
        last_beat = 0.0
        last_schedule = 0.0
        try:
            while not self.stop_event.is_set():
                if time.monotonic() - last_schedule >= 60:  # check the automatic schedule once a minute
                    last_schedule = time.monotonic()
                    self._schedule()
                claimed = analytics_sync.claim_job(self.worker_id)
                if claimed is not None:
                    self.run_job(*claimed)
                    if once:
                        break
                    continue
                if once:
                    break
                if time.monotonic() - last_beat >= self.settings.worker_heartbeat_seconds:
                    self.heartbeat()
                    last_beat = time.monotonic()
                interruptible_wait(self.stop_event, self.settings.analytics_poll_seconds)
        finally:
            self._shutdown()
        return 0

    def _shutdown(self) -> None:
        self.state = WorkerState.STOPPED
        self.current_job_id = None
        self.heartbeat()
        self._release_lock()
        log.info("Analytics worker stopped")

    # ------------------------------------------------------------- work
    def _schedule(self) -> None:
        try:
            with SessionLocal() as db:
                n = analytics_sync.enqueue_due_channels(db)
            if n:
                log.info("Queued %d scheduled analytics sync(s)", n)
        except Exception:  # noqa: BLE001
            log.exception("scheduling analytics syncs failed")

    def run_job(self, job_id: int, channel_id: int, payload: dict) -> None:
        self.current_job_id = job_id
        self.state = WorkerState.SYNCING
        self.heartbeat()
        try:
            result = analytics_sync.sync_channel(channel_id, http=self.http,
                                                 backfill_days=payload.get("backfill_days"),
                                                 heartbeat=self.heartbeat)
            analytics_sync.finish_job(job_id, ok=result.status != "error", error=result.error)
        except Exception as exc:  # noqa: BLE001 - never let one job kill the worker
            log.exception("Analytics job #%s crashed", job_id)
            analytics_sync.finish_job(job_id, ok=False, error=f"{exc.__class__.__name__}: {exc}")
        finally:
            self.current_job_id = None
            self.state = WorkerState.IDLE
            self.heartbeat()
