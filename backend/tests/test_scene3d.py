"""3D scene config + .glb model assets."""
import json
import struct

import pytest
from pydantic import ValidationError

from app.schemas.scene3d import Scene3D
from app.services.asset_service import inspect_glb
from app.services.errors import AppError


def make_glb(animations=("Idle", "Wave"), extra=None) -> bytes:
    doc = {"asset": {"version": "2.0", "generator": "test"}, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
           "meshes": [{"primitives": []}], "animations": [{"name": n, "channels": [], "samplers": []} for n in animations]}
    doc.update(extra or {})
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js)
    return struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(js), b"JSON") + js


def test_inspect_glb_reports_animations(tmp_path):
    p = tmp_path / "m.glb"
    p.write_bytes(make_glb())
    info = inspect_glb(p)
    assert info["meta"]["animations"] == ["Idle", "Wave"] and info["meta"]["meshes"] == 1


@pytest.mark.parametrize("data,msg", [
    (b"not a model at all, definitely", "glTF"),
    (make_glb()[:-8], "cắt cụt"),
    (make_glb(extra={"extensionsRequired": ["VENDOR_weird"]}), "extension"),
])
def test_inspect_glb_rejects_bad_files(tmp_path, data, msg):
    p = tmp_path / "bad.glb"
    p.write_bytes(data)
    with pytest.raises(AppError) as ei:
        inspect_glb(p)
    assert msg in str(ei.value)


def test_scene_defaults_and_validation():
    s = Scene3D()
    assert s.preset == "cozy_room" and s.environment.rain == 0.5
    with pytest.raises(ValidationError):
        Scene3D(environment={"rain": 2})
    with pytest.raises(ValidationError):
        Scene3D(character={"reactions": {"dance": "X"}})
    with pytest.raises(ValidationError):
        Scene3D(character={"position": (500, 0, 0)})
    with pytest.raises(ValidationError):
        Scene3D(preset="space_station")


def _project(client, ch, **kw):
    r = client.post(f"/api/channels/{ch['id']}/content",
                    json={"title": "Rainy room", "content_type": "rain_sounds", "duration_minutes": 30, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_upload_glb_and_use_in_scene(client, channel, upload_asset):
    ch = channel()
    r = upload_asset(make_glb(), "momo.glb", channel_id=ch["id"])
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["kind"] == "model" and a["mime_type"] == "model/gltf-binary"
    p = _project(client, ch, scene3d={"preset": "rainy_window", "character": {"asset_id": a["id"], "reactions": {"click": "Wave"}}})
    assert p["scene3d"]["preset"] == "rainy_window" and p["scene3d_model_url"].endswith(".glb")
    # editing the scene changes the render fingerprint (it is not just metadata)
    fp = p["fingerprint"]
    r = client.patch(f"/api/channels/{ch['id']}/content/{p['id']}",
                     json={"scene3d": {"preset": "cafe", "character": {"asset_id": a["id"]}}})
    assert r.status_code == 200 and r.json()["fingerprint"] != fp
    r = client.patch(f"/api/channels/{ch['id']}/content/{p['id']}", json={"clear_scene3d": True})
    assert r.json()["scene3d"] is None


def test_scene_rejects_non_model_and_foreign_assets(client, channel, upload_asset, png):
    ch, other = channel("a", "A"), channel("b", "B")
    img = upload_asset(png, "x.png", channel_id=ch["id"]).json()
    foreign = upload_asset(make_glb(), "f.glb", channel_id=other["id"]).json()
    for asset_id in (img["id"], foreign["id"]):
        r = client.post(f"/api/channels/{ch['id']}/content",
                        json={"title": "Bad scene", "content_type": "rain_sounds",
                              "scene3d": {"character": {"asset_id": asset_id}}})
        assert r.status_code in (400, 404), r.text


def test_corrupt_glb_upload_is_rejected(client, channel, upload_asset):
    ch = channel()
    r = client.post("/api/assets", data={"channel_id": str(ch["id"]), "license_type": "owned"},
                    files={"file": ("bad.glb", b"x" * 100, "model/gltf-binary")})
    assert r.status_code == 400
