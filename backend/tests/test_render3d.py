"""3D scene -> video through the real pipeline (headless Chromium + FFmpeg). Skipped when unavailable."""
import subprocess
import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

from app.core import storage
from app.render import ffmpeg as ff
from app.render import pipeline, scene3d
from app.schemas.scene3d import Scene3D
from app.worker.runner import RenderWorker
from conftest import has_ffmpeg

pytestmark = pytest.mark.skipif(not (has_ffmpeg() and scene3d.status()["available"]),
                                reason="ffmpeg + Chromium + built frontend (capture.html) required")


def plan3d(duration=8.0, loop=4.0, preset="cozy_room"):
    return {
        "version": 1, "title": "3D test", "width": 640, "height": 360, "fps": 30, "duration_sec": duration,
        "loop_seconds": 4, "video": {"crf": 26, "preset": "ultrafast", "max_bitrate_kbps": 1500},
        "audio": {"bitrate_kbps": 96}, "background": None, "character": None, "effects": [],
        "scene3d": {"scene": Scene3D(preset=preset).model_dump(mode="json"), "model_path": None,
                    "capture_fps": 15, "loop_seconds": loop},
        "layers": [{"kind": "generator", "generator": "rain", "volume": 0.7}],
        "overlay": {"mode": "none"}, "timeline": [], "chime": False, "seed": 1,
        "thumbnail": {"generate": True, "title_text": "Rainy night", "badge": "PREVIEW"},
    }


def _frames(video: Path, count: int) -> list[Path]:
    d = Path(tempfile.mkdtemp())
    subprocess.run([ff.ffmpeg_bin(), "-loglevel", "error", "-i", str(video), "-frames:v", str(count),
                    str(d / "f%04d.png")], check=True)
    return sorted(d.glob("f*.png"))


def _diff(a: Path, b: Path) -> float:
    return ImageStat.Stat(ImageChops.difference(Image.open(a).convert("L"), Image.open(b).convert("L"))).mean[0]


def test_pipeline_renders_seamless_3d_loop(tmp_path):
    out = tmp_path / "out"
    res = pipeline.render(plan3d(), resolve=storage.resolve, workdir=tmp_path / "work", output_dir=out,
                          log_file=tmp_path / "r.log", timeout=300)
    assert res.qc["passed"] and res.width == 640 and abs(res.duration - 8.0) < 0.2
    assert res.thumbnail_path is not None and res.thumbnail_path.exists()
    # 4 s loop @30 fps = 120 frames: frame 120 must be identical to frame 0 (no visible jump when it repeats)
    fr = _frames(res.video_path, 125)
    assert _diff(fr[0], fr[120]) < 0.05
    steps = [_diff(fr[i], fr[i + 1]) for i in range(0, 100)]
    assert _diff(fr[119], fr[120]) < max(steps) + 1.0
    # the picture is a real rendered room, not a blank frame
    assert ImageStat.Stat(Image.open(fr[10]).convert("L")).stddev[0] > 15


def test_cancel_during_capture(tmp_path):
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 3

    with pytest.raises(ff.RenderCancelled):
        pipeline.render(plan3d(), resolve=storage.resolve, workdir=tmp_path / "w", output_dir=tmp_path / "o",
                        log_file=tmp_path / "r.log", should_cancel=cancel, timeout=300)


def test_scene3d_project_renders_through_queue(client, channel):
    ch = channel("room3d", "Room 3D")
    r = client.post(f"/api/channels/{ch['id']}/content", json={
        "title": "Rainy room 3D", "content_type": "rain_sounds", "duration_minutes": 30,
        "scene3d": {"preset": "rainy_window", "environment": {"time_of_day": "night", "rain": 0.9}},
        "audio_layers": [{"kind": "generator", "generator": "rain", "volume": 0.7}],
        "render_settings": {"resolution": "1280x720"}})
    assert r.status_code == 201, r.text
    p = r.json()
    # no 2D background needed when a 3D scene exists
    v = client.get(f"/api/channels/{ch['id']}/content/{p['id']}/validate").json()
    assert v["ok"], v
    assert any("thay thế" in w for w in v["warnings"])
    job = client.post(f"/api/channels/{ch['id']}/content/{p['id']}/render",
                      json={"job_type": "preview", "preview_seconds": 12}).json()
    assert job["status"] == "queued"
    RenderWorker().run(once=True)
    j = client.get(f"/api/production/jobs/{job['id']}").json()
    assert j["status"] == "succeeded", j["error"]
    assert storage.resolve(j["output_url"].removeprefix("/media/")).stat().st_size > 10_000


def test_capabilities_report_scene3d(client):
    caps = client.get("/api/production/capabilities").json()
    assert caps["scene3d"]["available"] is True and caps["scene3d"]["chromium"]
