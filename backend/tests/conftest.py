"""Test setup: uses a real PostgreSQL database (TEST_DATABASE_URL), never the production DB."""
import io
import os
import tempfile

import pytest
from cryptography.fernet import Fernet

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://coco:coco@localhost:5432/coco_test")
os.environ["SECRET_KEY"] = Fernet.generate_key().decode()
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="coco-test-storage-")
os.environ["LOG_DIR"] = tempfile.mkdtemp(prefix="coco-test-logs-")
os.environ["DASHBOARD_PASSWORD"] = ""
# Phase 2: small loops/fast preset keep render tests quick; use bundled ffmpeg when none on PATH
os.environ.setdefault("RENDER_LOOP_SECONDS", "4")
os.environ.setdefault("RENDER_PRESET", "ultrafast")
os.environ.setdefault("MIN_FREE_DISK_GB", "0.5")
os.environ.setdefault("WORKER_HEARTBEAT_SECONDS", "1")
if not os.environ.get("FFMPEG_PATH"):
    import shutil as _sh
    if not _sh.which("ffmpeg"):
        try:
            import imageio_ffmpeg  # dev-only helper, not a runtime dependency
            os.environ["FFMPEG_PATH"] = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            pass

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean():
    yield
    names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client():
    return TestClient(app)


def make_png(color=(200, 150, 255), size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def png():
    return make_png


@pytest.fixture
def channel(client):
    def _make(code="cozy-study", name="Cozy Study", **kw):
        r = client.post("/api/channels", json={"code": code, "name": name, **kw})
        assert r.status_code == 201, r.text
        return r.json()
    return _make


def make_rgba_png(size=(200, 300)) -> bytes:
    """Transparent PNG with an opaque shape (character art)."""
    from PIL import ImageDraw
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([20, 80, size[0] - 20, size[1] - 10], fill=(240, 200, 160, 255))
    d.ellipse([50, 10, size[0] - 50, 120], fill=(240, 200, 160, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def make_wav(seconds=2.0, freq=440.0) -> bytes:
    import math
    import struct
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / 22050)))
                          for i in range(int(seconds * 22050)))
        w.writeframes(frames)
    return buf.getvalue()


def has_ffmpeg() -> bool:
    try:
        from app.render.ffmpeg import ffmpeg_bin
        ffmpeg_bin()
        return True
    except Exception:
        return False


@pytest.fixture
def upload_asset(client):
    def _up(data: bytes, filename: str, channel_id=None, license_type="owned", **kw):
        form = {"license_type": license_type, **{k: str(v) for k, v in kw.items()}}
        if channel_id is not None:
            form["channel_id"] = str(channel_id)
        return client.post("/api/assets", data=form, files={"file": (filename, data)})
    return _up


@pytest.fixture
def character_with_art(client):
    def _make(channel_id: int, name="Momo", role="primary"):
        r = client.post(f"/api/channels/{channel_id}/characters", json={"name": name, "role": role})
        assert r.status_code == 201, r.text
        cid = r.json()["id"]
        r = client.post(f"/api/channels/{channel_id}/characters/{cid}/images", data={"slot": "full_body"},
                        files={"file": ("momo.png", make_rgba_png())})
        assert r.status_code == 201, r.text
        return r.json()
    return _make


@pytest.fixture
def background(client):
    def _make(channel_id=None, style="bokeh", seed=1):
        r = client.post("/api/assets/generate-background",
                        json={"channel_id": channel_id, "style": style, "seed": seed})
        assert r.status_code == 201, r.text
        return r.json()
    return _make
