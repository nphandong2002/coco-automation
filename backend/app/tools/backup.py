"""Backup / restore for the portable (Windows) install: one .zip with the database dump, .env and storage.

    python -m app.tools.backup create [--db-only]
    python -m app.tools.backup restore <file.zip> [--with-env] [--yes]

The archive layout matches scripts/backup.sh (database.dump, env.backup, storage/...), only zip instead of tar.gz.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import PROJECT_ROOT, get_settings


def _pg_tool(name: str) -> str:
    s = get_settings()
    if s.embedded_pg:
        from app.tools.embedded_pg import bin_path
        return bin_path(name)
    found = shutil.which(name)
    if not found:
        sys.exit(f"Không tìm thấy {name}. Cài PostgreSQL client tools và thêm vào PATH.")
    return found


def _pg_env() -> tuple[dict, list[str]]:
    u = make_url(get_settings().database_url)
    env = {**os.environ, "PGPASSWORD": u.password or ""}
    conn = ["-h", u.host or "127.0.0.1", "-p", str(u.port or 5432), "-U", u.username or "coco"]
    return env, [*conn, "-d", u.database or "coco"]


KEEP_LOCAL_KEYS = ("DATABASE_URL", "EMBEDDED_PG")


def merge_env(restored: str, local: str) -> str:
    """Take the restored .env but keep this machine's database settings (see restore())."""
    import re
    out = restored
    for key in KEEP_LOCAL_KEYS:
        m = re.search(rf"^{key}=.*$", local, re.M)
        if not m:
            continue
        if re.search(rf"^{key}=.*$", out, re.M):
            out = re.sub(rf"^{key}=.*$", lambda _: m.group(0), out, count=1, flags=re.M)
        else:
            out = out.rstrip("\n") + "\n" + m.group(0) + "\n"
    return out


def create(db_only: bool = False) -> Path:
    s = get_settings()
    out_dir = PROJECT_ROOT / "backups"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"coco-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    env, conn = _pg_env()
    with tempfile.TemporaryDirectory() as work:
        dump = Path(work) / "database.dump"
        print("Dump PostgreSQL...")
        r = subprocess.run([_pg_tool("pg_dump"), "--format=custom", "--no-owner", f"--file={dump}", *conn],
                           env=env, capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"pg_dump thất bại: {r.stderr.strip()}")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            z.write(dump, "database.dump")
            env_file = PROJECT_ROOT / ".env"
            if env_file.exists():
                z.write(env_file, "env.backup")
            storage = Path(s.storage_dir)
            if not db_only and storage.is_dir():
                print(f"Đóng gói storage ({storage})...")
                for p in storage.rglob("*"):
                    if p.is_file() and "tmp" not in p.relative_to(storage).parts[:1]:
                        # video is already compressed: store, do not deflate (fast, no RAM)
                        z.write(p, "storage/" + p.relative_to(storage).as_posix(), compress_type=zipfile.ZIP_STORED)
    print(f"Đã tạo {out} ({out.stat().st_size / 1024**2:.1f} MB)")
    print("Lưu ý: file chứa .env (SECRET_KEY). Cất giữ an toàn.")
    return out


def restore(archive: Path, with_env: bool, assume_yes: bool) -> None:
    if not archive.is_file():
        sys.exit(f"Không thấy file {archive}")
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if "database.dump" not in names:
            sys.exit("Archive không hợp lệ (thiếu database.dump)")
        if not assume_yes and input("Khôi phục sẽ GHI ĐÈ dữ liệu hiện tại. Gõ 'yes' để tiếp tục: ").strip() != "yes":
            sys.exit("Đã hủy.")
        if with_env and "env.backup" in names:
            current = PROJECT_ROOT / ".env"
            old_text = current.read_text(encoding="utf-8") if current.exists() else ""
            if current.exists():
                shutil.copy2(current, PROJECT_ROOT / ".env.before-restore")
            # SECRET_KEY etc. come from the backup, but the database connection stays THIS machine's:
            # the private PostgreSQL here was created with its own password/port.
            current.write_text(merge_env(z.read("env.backup").decode("utf-8"), old_text), encoding="utf-8", newline="")
            print("Đã khôi phục .env (bản cũ: .env.before-restore; giữ nguyên DATABASE_URL của máy này)")
        if get_settings().embedded_pg:
            from app.tools import embedded_pg
            embedded_pg.ensure()
        with tempfile.TemporaryDirectory() as work:
            z.extract("database.dump", work)
            env, conn = _pg_env()
            print("Khôi phục database...")
            r = subprocess.run([_pg_tool("pg_restore"), "--clean", "--if-exists", "--no-owner", *conn,
                                str(Path(work) / "database.dump")], env=env, capture_output=True, text=True)
            if r.returncode not in (0, 1):  # 1 = warnings (e.g. objects that did not exist yet)
                sys.exit(f"pg_restore thất bại: {r.stderr.strip()}")
        storage = Path(get_settings().storage_dir)
        members = [n for n in names if n.startswith("storage/") and not n.endswith("/")]
        if members:
            print(f"Khôi phục {len(members)} file storage → {storage}")
            for n in members:
                target = (storage / n[len("storage/"):]).resolve()
                if storage.resolve() not in target.parents:  # zip-slip guard
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(n) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
    print("Xong. Chạy: coco start")


def main() -> int:
    ap = argparse.ArgumentParser(prog="app.tools.backup")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--db-only", action="store_true")
    r = sub.add_parser("restore")
    r.add_argument("archive", type=Path)
    r.add_argument("--with-env", action="store_true")
    r.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if a.cmd == "create":
        create(a.db_only)
    else:
        restore(a.archive, a.with_env, a.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
