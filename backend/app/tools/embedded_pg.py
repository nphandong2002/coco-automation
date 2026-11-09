"""Private PostgreSQL for the portable/Windows install (no admin rights, no system service).

Uses the PostgreSQL binaries shipped by the `pgserver` pip package, with a data directory under
`data/pgdata`, bound to 127.0.0.1 and protected by the password in DATABASE_URL (scram-sha-256).

    python -m app.tools.embedded_pg init|start|stop|status|ensure
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg
from sqlalchemy.engine import make_url

from app.core.config import get_settings

WIN = sys.platform == "win32"
# keep the server alive when the console / supervisor receives Ctrl+C
_DETACH = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
           | getattr(subprocess, "CREATE_NO_WINDOW", 0)) if WIN else 0
# modest settings for an 8 GB PC that also renders video
SERVER_OPTS = ["-c", "listen_addresses=127.0.0.1", "-c", "shared_buffers=256MB", "-c", "max_connections=60",
               "-c", "work_mem=8MB", "-c", "synchronous_commit=on"]


class EmbeddedPgError(RuntimeError):
    pass


def bin_path(name: str) -> str:
    try:
        import pgserver
    except ImportError as exc:  # pragma: no cover
        raise EmbeddedPgError("Thiếu gói 'pgserver'. Chạy: pip install -r backend/requirements-windows.txt") from exc
    exe = Path(pgserver.__file__).parent / "pginstall" / "bin" / (name + (".exe" if WIN else ""))
    if not exe.is_file():
        raise EmbeddedPgError(f"Không tìm thấy {exe}")
    return str(exe)


def _url():  # noqa: ANN202
    return make_url(get_settings().database_url)


def data_dir() -> Path:
    return Path(get_settings().pg_data_dir)


def _log_file() -> Path:
    d = get_settings().log_dir
    d.mkdir(parents=True, exist_ok=True)
    return d / "postgres.log"  # deliberately OUTSIDE the data dir (an open log inside it blocks crash recovery on Windows)


def _run(args: list[str], timeout: float = 120, **kw) -> subprocess.CompletedProcess:  # noqa: ANN003
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kw)


def is_initialised() -> bool:
    return (data_dir() / "PG_VERSION").is_file()


def is_running() -> bool:
    if not is_initialised():
        return False
    return _run([bin_path("pg_ctl"), "status", "-D", str(data_dir())], timeout=30).returncode == 0


def init() -> bool:
    """Create the cluster once. Returns True if it was created now."""
    if is_initialised():
        return False
    url = _url()
    data_dir().parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".pw") as f:
        f.write(url.password or "")
        pwfile = f.name
    try:
        r = _run([bin_path("initdb"), "-D", str(data_dir()), "-U", url.username or "coco", "-E", "UTF8",
                  "--locale=C", "--auth=scram-sha-256", f"--pwfile={pwfile}"], timeout=300)
    finally:
        os.unlink(pwfile)
    if r.returncode != 0:
        raise EmbeddedPgError(f"initdb thất bại: {r.stderr.strip() or r.stdout.strip()}")
    return True


def start() -> bool:
    """Start the server (idempotent). Returns True if it was started now."""
    if not is_initialised():
        init()
    if is_running():
        return False
    port = _url().port or 5432
    opts = " ".join(["-p", str(port), *SERVER_OPTS])
    # NOT capture_output: the server inherits the handles and would keep a pipe open forever
    # (subprocess.run would never return). Server messages go to the log file instead.
    r = subprocess.run([bin_path("pg_ctl"), "start", "-D", str(data_dir()), "-w", "-t", "120",
                        "-l", str(_log_file()), "-o", opts],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=180, creationflags=_DETACH)
    if r.returncode != 0:
        raise EmbeddedPgError(f"PostgreSQL không khởi động được (xem {_log_file()})")
    return True


def stop() -> bool:
    if not is_running():
        return False
    r = _run([bin_path("pg_ctl"), "stop", "-D", str(data_dir()), "-m", "fast", "-w", "-t", "90"], timeout=120)
    if r.returncode != 0:
        raise EmbeddedPgError(f"Không dừng được PostgreSQL: {r.stderr.strip()}")
    return True


def ensure_database() -> bool:
    """Create the application database when missing. Returns True if created."""
    url = _url()
    with psycopg.connect(host=url.host or "127.0.0.1", port=url.port or 5432, user=url.username,
                         password=url.password, dbname="postgres", autocommit=True, connect_timeout=15) as c:
        if c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (url.database,)).fetchone():
            return False
        c.execute(f'CREATE DATABASE "{url.database}" ENCODING \'UTF8\' TEMPLATE template0')
        return True


def ensure() -> None:
    """init + start + create database: everything the supervisor needs before running migrations."""
    init()
    start()
    ensure_database()


def main(argv: list[str] | None = None) -> int:
    cmd = (argv or sys.argv[1:] or ["status"])[0]
    try:
        if cmd == "init":
            print("đã tạo" if init() else "đã có sẵn")
        elif cmd == "start":
            print("đã khởi động" if start() else "đang chạy")
        elif cmd == "stop":
            print("đã dừng" if stop() else "không chạy")
        elif cmd == "ensure":
            ensure()
            print("sẵn sàng")
        elif cmd == "status":
            print("running" if is_running() else "stopped")
            return 0 if is_running() else 1
        else:
            print("Cách dùng: python -m app.tools.embedded_pg init|start|stop|status|ensure")
            return 2
    except EmbeddedPgError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
