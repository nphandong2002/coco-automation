"""Cross-platform process supervisor (the Windows counterpart of scripts/run.sh).

Starts (optionally) the embedded PostgreSQL, applies migrations, then runs the API and the five
workers as child processes:
  * a child that exits is restarted after RESTART_DELAY seconds;
  * the API is also health-checked every 30 s and restarted after 3 failures in a row;
  * stop = create `run/stop.request` (coco stop) or Ctrl+C / SIGTERM: children get a graceful stop signal
    (CTRL_BREAK on Windows, SIGTERM elsewhere), then are killed after STOP_GRACE seconds.
    Unfinished jobs are recovered on the next start (see docs/OPERATIONS.md).

    python -m app.tools.supervisor
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import PROJECT_ROOT, get_settings

log = logging.getLogger("coco.supervisor")
WIN = sys.platform == "win32"
RESTART_DELAY = 5.0
STOP_GRACE = 60.0
HEALTH_EVERY = 30.0
HEALTH_FAILS = 3
WORKERS = ("render", "publish", "analytics", "monitor")


@dataclass
class Child:
    name: str
    cmd: list[str]
    proc: subprocess.Popen | None = None
    restart_at: float = 0.0
    starts: int = 0
    env: dict[str, str] | None = None


@dataclass
class Supervisor:
    children: list[Child]
    stop_file: Path
    cwd: Path
    health_url: str | None = None
    restart_delay: float = RESTART_DELAY
    stop_grace: float = STOP_GRACE
    health_every: float = HEALTH_EVERY
    _stop: bool = False
    _fails: int = 0
    _next_health: float = field(default=0.0)
    _started_at: float = field(default=0.0)

    # ------------------------------------------------------------- child control
    def _spawn(self, c: Child) -> None:
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if WIN else 0
        env = {**os.environ, **(c.env or {})}
        c.proc = subprocess.Popen(c.cmd, cwd=str(self.cwd), env=env, creationflags=flags)
        c.starts += 1
        log.info("started %s (pid %s, start #%d)", c.name, c.proc.pid, c.starts)

    @staticmethod
    def _graceful(c: Child) -> None:
        if c.proc is None or c.proc.poll() is not None:
            return
        try:
            if WIN:
                c.proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            else:
                c.proc.terminate()
        except (OSError, ValueError):
            pass

    def restart_child(self, name: str) -> None:
        for c in self.children:
            if c.name == name and c.proc is not None and c.proc.poll() is None:
                self._graceful(c)
                try:
                    c.proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    c.proc.kill()

    # ------------------------------------------------------------- main loop
    def request_stop(self) -> None:
        self._stop = True

    def _health_ok(self) -> bool:
        try:
            with urllib.request.urlopen(self.health_url, timeout=10) as r:  # type: ignore[arg-type]
                return r.status == 200
        except Exception:  # noqa: BLE001
            return False

    def tick(self) -> None:
        now = time.monotonic()
        if self.stop_file.exists():
            self._stop = True
        for c in self.children:
            if c.proc is None:
                if now >= c.restart_at:
                    self._spawn(c)
            elif c.proc.poll() is not None:
                log.warning("%s exited with code %s — restarting in %.0fs", c.name, c.proc.returncode, self.restart_delay)
                c.proc, c.restart_at = None, now + self.restart_delay
        if self.health_url and now >= self._next_health:
            self._next_health = now + self.health_every
            api = next((c for c in self.children if c.name == "api"), None)
            if api and api.proc is not None and api.proc.poll() is None and now - self._started_at > 60:
                if self._health_ok():
                    self._fails = 0
                else:
                    self._fails += 1
                    log.warning("API health check failed (%d/%d)", self._fails, HEALTH_FAILS)
                    if self._fails >= HEALTH_FAILS:
                        self._fails = 0
                        log.error("API unresponsive — restarting it")
                        self.restart_child("api")

    def run(self) -> int:
        self._started_at = time.monotonic()
        self.stop_file.unlink(missing_ok=True)
        try:
            while not self._stop:
                self.tick()
                time.sleep(1.0)
        except KeyboardInterrupt:
            log.info("Ctrl+C — stopping")
        self.shutdown()
        return 0

    def shutdown(self) -> None:
        log.info("stopping %d child process(es)…", sum(1 for c in self.children if c.proc and c.proc.poll() is None))
        for c in self.children:
            self._graceful(c)
        deadline = time.monotonic() + self.stop_grace
        for c in self.children:
            if c.proc is None:
                continue
            try:
                c.proc.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                log.warning("%s did not stop in %.0fs — killing", c.name, self.stop_grace)
                c.proc.kill()
                c.proc.wait(timeout=10)
        self.stop_file.unlink(missing_ok=True)


# ---------------------------------------------------------------- production wiring
def build_children() -> list[Child]:
    s = get_settings()
    py = sys.executable
    api = Child("api", [py, "-m", "uvicorn", "app.main:app", "--host", s.host, "--port", str(s.port), "--workers", "1",
                        "--proxy-headers", "--timeout-graceful-shutdown", "30"])
    return [api, *[Child(w, [py, "-m", "app.worker", "--kind", w]) for w in WORKERS]]


def main() -> int:
    from app.core.logging_setup import setup_logging
    setup_logging()
    s = get_settings()
    backend = PROJECT_ROOT / "backend"
    run_dir = PROJECT_ROOT / "run"
    run_dir.mkdir(exist_ok=True)
    pid_file = run_dir / "coco.pid"
    pid_file.write_text(str(os.getpid()))
    try:
        if s.embedded_pg:
            from app.tools import embedded_pg
            log.info("starting embedded PostgreSQL…")
            embedded_pg.ensure()
        log.info("applying database migrations…")
        r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=str(backend))
        if r.returncode != 0:
            log.error("migration failed (exit %s) — not starting", r.returncode)
            return 1
        if not (s.frontend_dist / "index.html").exists():
            log.warning("Frontend chưa build — dashboard sẽ không hiển thị (chạy scripts\\windows\\install.ps1)")
        host = "127.0.0.1" if s.host in ("0.0.0.0", "::") else s.host
        sup = Supervisor(build_children(), run_dir / "stop.request", backend, f"http://{host}:{s.port}/api/health")
        if not WIN:
            signal.signal(signal.SIGTERM, lambda *_: sup.request_stop())
        elif hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, lambda *_: sup.request_stop())
        log.info("Coco Automation: http://%s:%s (API + %s workers)", host, s.port, len(WORKERS))
        code = sup.run()
    finally:
        if s.embedded_pg:
            try:
                from app.tools import embedded_pg
                embedded_pg.stop()
            except Exception:  # noqa: BLE001
                log.exception("could not stop embedded PostgreSQL")
        pid_file.unlink(missing_ok=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
