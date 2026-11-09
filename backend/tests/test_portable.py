"""Portable/Windows install: supervisor, .env generator, embedded PostgreSQL, zip backup/restore."""
import socket
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import psycopg
import pytest
from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.tools import backup, embedded_pg, make_env
from app.tools.supervisor import Child, Supervisor


def py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


# ============================================================ supervisor
def test_supervisor_restarts_crashed_child_and_stops_cleanly(tmp_path):
    marker = tmp_path / "starts.txt"
    crash = py(f"open(r'{marker}', 'a').write('x'); import sys; sys.exit(3)")   # dies immediately
    steady = py("import time; time.sleep(120)")
    sup = Supervisor([Child("crashy", crash), Child("steady", steady)], tmp_path / "stop.request", tmp_path,
                     restart_delay=0.3, stop_grace=10)
    sup._started_at = time.monotonic()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and len(marker.read_text() if marker.exists() else "") < 3:
        sup.tick()
        time.sleep(0.2)
    assert len(marker.read_text()) >= 3                       # restarted again and again
    steady_child = sup.children[1]
    assert steady_child.starts == 1 and steady_child.proc.poll() is None   # healthy sibling untouched
    (tmp_path / "stop.request").write_text("")
    sup.tick()
    assert sup._stop is True
    sup.shutdown()
    assert steady_child.proc.poll() is not None                 # stopped
    assert not (tmp_path / "stop.request").exists()


def test_supervisor_kills_child_that_ignores_the_stop_signal(tmp_path):
    sup = Supervisor([Child("deaf", py("import signal, time\n"
                                       "for s in ('SIGTERM', 'SIGBREAK', 'SIGINT'):\n"
                                       "    if hasattr(signal, s): signal.signal(getattr(signal, s), signal.SIG_IGN)\n"
                                       "print('ready', flush=True); time.sleep(120)"))],
                     tmp_path / "stop.request", tmp_path, stop_grace=2)
    sup.tick()
    time.sleep(1.0)                                              # let the child install its handlers
    t = time.monotonic()
    sup.shutdown()
    assert sup.children[0].proc.poll() is not None and time.monotonic() - t < 15


# ============================================================ .env generator
def test_make_env_embedded_defaults():
    example = Path(__file__).resolve().parents[2].joinpath(".env.example").read_text(encoding="utf-8")
    env, dash = make_env.build(example, None, 8095)
    kv = dict(line.split("=", 1) for line in env.splitlines() if "=" in line and not line.startswith("#"))
    Fernet(kv["SECRET_KEY"].encode())                            # valid Fernet key
    assert kv["EMBEDDED_PG"] == "true" and kv["PORT"] == "8095"
    assert kv["DATABASE_URL"].startswith("postgresql+psycopg://coco:") and f":{make_env.PG_PORT}/coco" in kv["DATABASE_URL"]
    assert "CHANGE_ME" not in env and kv["DASHBOARD_PASSWORD"] == dash and len(dash) >= 10
    assert kv["OAUTH_REDIRECT_URI"] == "http://localhost:8095/api/youtube/oauth/callback"
    again, _ = make_env.build(example, None, 8095)
    assert again != env                                          # fresh secrets every time


def test_make_env_external_database():
    env, _ = make_env.build("DATABASE_URL=x\nSECRET_KEY=\nDASHBOARD_PASSWORD=\nPORT=1\n", "postgresql+psycopg://u:p@db:5432/x", 80)
    assert "EMBEDDED_PG=false" in env and "DATABASE_URL=postgresql+psycopg://u:p@db:5432/x" in env


# ============================================================ embedded PostgreSQL + backup (real server)
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def private_pg(tmp_path, monkeypatch):
    s = get_settings()
    port = _free_port()
    monkeypatch.setattr(s, "embedded_pg", True)
    monkeypatch.setattr(s, "pg_data_dir", tmp_path / "pgdata")
    monkeypatch.setattr(s, "database_url", f"postgresql+psycopg://coco:s3cret@127.0.0.1:{port}/cocodb")
    monkeypatch.setattr(s, "storage_dir", tmp_path / "storage")
    monkeypatch.setattr(backup, "PROJECT_ROOT", tmp_path)
    yield tmp_path, port
    try:
        embedded_pg.stop()
    except Exception:  # noqa: BLE001
        pass


def test_embedded_postgres_lifecycle_and_backup_restore(private_pg):
    tmp, port = private_pg
    assert embedded_pg.is_running() is False
    embedded_pg.ensure()
    assert embedded_pg.is_running() is True and embedded_pg.ensure_database() is False   # idempotent
    assert embedded_pg.start() is False                                                   # already running

    def conn():  # noqa: ANN202
        return psycopg.connect(host="127.0.0.1", port=port, user="coco", password="s3cret", dbname="cocodb",
                               autocommit=True, connect_timeout=10)

    with conn() as c:
        c.execute("CREATE TABLE t (v text)")
        c.execute("INSERT INTO t VALUES ('keep-me')")
    with pytest.raises(psycopg.OperationalError):                                         # password is enforced
        psycopg.connect(host="127.0.0.1", port=port, user="coco", password="wrong", dbname="cocodb", connect_timeout=5)

    # storage + .env go into the zip, tmp/ is skipped
    (tmp / "storage" / "channels" / "1").mkdir(parents=True)
    (tmp / "storage" / "channels" / "1" / "video.mp4").write_bytes(b"VIDEO")
    (tmp / "storage" / "tmp").mkdir()
    (tmp / "storage" / "tmp" / "scratch.bin").write_bytes(b"x")
    (tmp / ".env").write_text("SECRET_KEY=abc\n")
    out = backup.create()
    names = zipfile.ZipFile(out).namelist()
    assert "database.dump" in names and "env.backup" in names and "storage/channels/1/video.mp4" in names
    assert not any("scratch.bin" in n for n in names)

    # damage everything, then restore
    with conn() as c:
        c.execute("DROP TABLE t")
    (tmp / "storage" / "channels" / "1" / "video.mp4").unlink()
    (tmp / ".env").write_text("SECRET_KEY=changed\n")
    backup.restore(out, with_env=True, assume_yes=True)
    with conn() as c:
        assert c.execute("SELECT v FROM t").fetchone() == ("keep-me",)
    assert (tmp / "storage" / "channels" / "1" / "video.mp4").read_bytes() == b"VIDEO"
    assert (tmp / ".env").read_text() == "SECRET_KEY=abc\n" and (tmp / ".env.before-restore").exists()

    assert embedded_pg.stop() is True and embedded_pg.is_running() is False
    assert embedded_pg.stop() is False


def test_restore_rejects_bad_archive_and_zip_slip(private_pg, tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("hello.txt", "x")
    with pytest.raises(SystemExit):
        backup.restore(bad, with_env=False, assume_yes=True)
    with pytest.raises(SystemExit):
        backup.restore(tmp_path / "missing.zip", with_env=False, assume_yes=True)


def test_restore_keeps_local_database_url_but_takes_secret_key():
    restored = "\n".join(["SECRET_KEY=from-backup", "DATABASE_URL=postgresql+psycopg://old:oldpw@h:1/x", "PORT=9", ""])
    local = "\n".join(["DATABASE_URL=postgresql+psycopg://coco:newpw@127.0.0.1:54329/coco", "EMBEDDED_PG=true", ""])
    merged = backup.merge_env(restored, local)
    assert "SECRET_KEY=from-backup" in merged and "PORT=9" in merged
    assert "DATABASE_URL=postgresql+psycopg://coco:newpw@127.0.0.1:54329/coco" in merged and "oldpw" not in merged
    assert "EMBEDDED_PG=true" in merged
