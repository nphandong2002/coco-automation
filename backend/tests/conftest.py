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
