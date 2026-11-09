"""Monitor worker: samples system metrics every minute, runs the hung-job watchdog and hourly maintenance.

Single instance (advisory lock). It never touches business data except to recover jobs that are provably
stuck (see services/recovery.py).
"""
from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.models import WorkerStatus
from app.models.enums import WorkerState
from app.services import monitor_service, recovery

log = logging.getLogger("coco.monitor")
MONITOR_LOCK_KEY = 72_700_004
MAINTENANCE_EVERY_SEC = 3600


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MonitorWorker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:monitor"
        self.stop_event = threading.Event()
        self.lock_conn = None
        self.state = WorkerState.IDLE

    def _install_signals(self) -> None:
        def _handler(signum, _frame):  # noqa: ANN001
            log.info("Signal %s received, stopping…", signum)
            self.stop_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                pass

    def _acquire_lock(self) -> bool:
        conn = engine.connect()
        got = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": MONITOR_LOCK_KEY}).scalar()
        conn.commit()
        if got:
            self.lock_conn = conn
            return True
        conn.close()
        return False

    def _release_lock(self) -> None:
        if self.lock_conn is not None:
            try:
                self.lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": MONITOR_LOCK_KEY})
                self.lock_conn.commit()
            finally:
                self.lock_conn.close()
                self.lock_conn = None

    def heartbeat(self) -> None:
        try:
            with SessionLocal() as db:
                w = db.get(WorkerStatus, self.worker_id)
                if w is None:
                    w = WorkerStatus(worker_id=self.worker_id, kind="monitor", hostname=socket.gethostname(),
                                     pid=os.getpid(), started_at=_now(), info={})
                    db.add(w)
                w.state = self.state
                w.heartbeat_at = _now()
                db.commit()
        except Exception:  # noqa: BLE001
            log.exception("heartbeat failed")

    def tick(self, run_maintenance: bool = False) -> None:
        """One monitoring cycle. Each step is isolated: a failure in one must not skip the others."""
        self.heartbeat()
        try:
            with SessionLocal() as db:
                actions = recovery.watchdog(db)
            for act in actions:
                log.warning("watchdog: %s", act)
        except Exception:  # noqa: BLE001
            log.exception("watchdog failed")
        try:
            with SessionLocal() as db:
                monitor_service.record_sample(db)
        except Exception:  # noqa: BLE001
            log.exception("metric sampling failed")
        if run_maintenance:
            try:
                with SessionLocal() as db:
                    log.info("maintenance: %s", recovery.maintenance(db))
            except Exception:  # noqa: BLE001
                log.exception("maintenance failed")

    def run(self, once: bool = False) -> int:
        self._install_signals()
        self.state = WorkerState.WAITING_LOCK
        self.heartbeat()
        while not self.stop_event.is_set():
            if self._acquire_lock():
                break
            self.heartbeat()
            self.stop_event.wait(10)
        if self.stop_event.is_set():
            self._shutdown()
            return 0
        log.info("Monitor lock acquired (%s)", self.worker_id)
        self.state = WorkerState.IDLE
        last_maint = 0.0
        try:
            while not self.stop_event.is_set():
                due = time.monotonic() - last_maint >= MAINTENANCE_EVERY_SEC
                if due:
                    last_maint = time.monotonic()
                self.tick(run_maintenance=due)
                if once:
                    break
                self.stop_event.wait(self.settings.monitor_interval_seconds)
        finally:
            self._shutdown()
        return 0

    def _shutdown(self) -> None:
        self.state = WorkerState.STOPPED
        self.heartbeat()
        self._release_lock()
        log.info("Monitor worker stopped")
