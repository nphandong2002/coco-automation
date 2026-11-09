"""Create `.env` for the portable (Windows) install. Never overwrites an existing file.

    python -m app.tools.make_env [--external-db URL] [--port 8080]

Prints the dashboard credentials once; they are stored in `.env` (edit it to change them).
"""
from __future__ import annotations

import argparse
import re
import secrets
import shutil
import sys
from pathlib import Path

from cryptography.fernet import Fernet

from app.core.config import PROJECT_ROOT

PG_PORT = 54329  # private PostgreSQL port (avoids clashing with a system PostgreSQL on 5432)


def find_ffmpeg() -> str:
    """Prefer an ffmpeg on PATH; fall back to the binary bundled by imageio-ffmpeg."""
    found = shutil.which("ffmpeg")
    if found:
        return ""  # empty = use PATH
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return ""


def build(example: str, external_db: str | None, port: int) -> tuple[str, str]:
    dash_pass = secrets.token_urlsafe(10)
    if external_db:
        db_url, embedded = external_db, "false"
    else:
        db_url = f"postgresql+psycopg://coco:{secrets.token_urlsafe(24)}@127.0.0.1:{PG_PORT}/coco"
        embedded = "true"
    ffmpeg = find_ffmpeg().replace("\\", "/")

    def setv(text: str, key: str, value: str) -> str:
        line = f"{key}={value}"
        if re.search(rf"^{key}=.*$", text, re.M):
            return re.sub(rf"^{key}=.*$", lambda _: line, text, count=1, flags=re.M)
        return text.rstrip("\n") + f"\n{line}\n"

    env = example
    env = setv(env, "DATABASE_URL", db_url)
    env = setv(env, "SECRET_KEY", Fernet.generate_key().decode())
    env = setv(env, "DASHBOARD_PASSWORD", dash_pass)
    env = setv(env, "PORT", str(port))
    env = setv(env, "OAUTH_REDIRECT_URI", f"http://localhost:{port}/api/youtube/oauth/callback")
    env = setv(env, "EMBEDDED_PG", embedded)
    if ffmpeg:
        env = setv(env, "FFMPEG_PATH", ffmpeg)
    return env, dash_pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--external-db", default=None, help="use your own PostgreSQL (SQLAlchemy URL) instead of the embedded one")
    ap.add_argument("--port", type=int, default=8080)
    a = ap.parse_args()
    target = PROJECT_ROOT / ".env"
    if target.exists():
        print(".env đã có — giữ nguyên.")
        return 0
    env, dash = build((PROJECT_ROOT / ".env.example").read_text(encoding="utf-8"), a.external_db, a.port)
    target.write_text(env, encoding="utf-8")
    print(f"Đã tạo .env — đăng nhập dashboard: admin / {dash}")
    print(">>> SAO LƯU file .env (đặc biệt SECRET_KEY) ở nơi an toàn <<<")
    return 0


if __name__ == "__main__":
    sys.exit(main())
