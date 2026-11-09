"""Post-render quality control.

Hard checks (fail the job): container, H.264/yuv420p, resolution, fps, AAC 48 kHz stereo,
duration within tolerance, audio not silent.
Soft checks (warnings): frames sampled at 10/50/90 % are not black.
"""
from __future__ import annotations

import io
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageStat

from app.render.ffmpeg import ffmpeg_bin, run_capture
from app.render.probe import probe

SILENCE_DB = -70.0
BLACK_LUMA = 8.0


def _check(checks: list, name: str, ok: bool, detail: str, critical: bool = True) -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail, "critical": critical})


def _frame_luma(path: Path, at: float) -> float | None:
    raw = subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", str(path),
         "-frames:v", "1", "-vf", "scale=160:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True, timeout=120,
    ).stdout
    if not raw:
        return None
    with Image.open(io.BytesIO(raw)) as im:
        return float(ImageStat.Stat(im.convert("L")).mean[0])


def _mean_volume(path: Path, at: float, length: float = 6.0) -> float | None:
    out = run_capture(["-ss", f"{at:.2f}", "-t", f"{length:.2f}", "-i", str(path), "-vn",
                       "-af", "volumedetect", "-f", "null", "-"], timeout=180)
    m = re.search(r"mean_volume:\s*(-?[\d.]+|-inf)\s*dB", out.stderr)
    if not m:
        return None
    return float("-inf") if m.group(1) == "-inf" else float(m.group(1))


def check_video(path: Path, *, width: int, height: int, fps: float, duration: float,
                sample_rate: int = 48000) -> dict:
    checks: list[dict] = []
    try:
        info = probe(path)
    except Exception as exc:  # noqa: BLE001
        _check(checks, "probe", False, f"Không đọc được file: {exc}")
        return {"passed": False, "checks": checks, "info": None}

    v, a = info.get("video") or {}, info.get("audio") or {}
    _check(checks, "container", "mp4" in (info.get("format_name") or "") or "mov" in (info.get("format_name") or ""),
           info.get("format_name") or "?")
    _check(checks, "video_codec", v.get("codec") == "h264", str(v.get("codec")))
    _check(checks, "pixel_format", (v.get("pix_fmt") or "yuv420p").startswith("yuv420p"), str(v.get("pix_fmt")))
    _check(checks, "resolution", (v.get("width"), v.get("height")) == (width, height),
           f"{v.get('width')}x{v.get('height')} (cần {width}x{height})")
    _check(checks, "fps", v.get("fps") is not None and abs(float(v["fps"]) - fps) < 0.05,
           f"{v.get('fps')} (cần {fps})")
    _check(checks, "audio_codec", a.get("codec") == "aac", str(a.get("codec")))
    _check(checks, "audio_sample_rate", a.get("sample_rate") == sample_rate, f"{a.get('sample_rate')} Hz")
    _check(checks, "audio_channels", a.get("channels") == 2, str(a.get("channels")))
    got = info.get("duration") or 0.0
    tol = max(1.0, duration * 0.002)
    _check(checks, "duration", abs(got - duration) <= tol, f"{got:.2f}s (cần {duration:.2f}s ±{tol:.1f})")
    _check(checks, "file_size", (info.get("size") or 0) > 0, f"{info.get('size')} bytes")

    samples = (0.1, 0.5, 0.9)
    vols, lumas = [], []
    for frac in samples:
        at = max(0.0, min(duration - 1.0, duration * frac))
        vols.append(_mean_volume(path, at, min(6.0, max(1.0, duration - at))))
        lumas.append(_frame_luma(path, at))
    real_vols = [x for x in vols if x is not None]
    _check(checks, "audio_not_silent", bool(real_vols) and max(real_vols) > SILENCE_DB,
           "mean volume: " + ", ".join("?" if x is None else f"{x:.1f} dB" for x in vols))
    real_l = [x for x in lumas if x is not None]
    _check(checks, "frames_not_black", bool(real_l) and min(real_l) > BLACK_LUMA,
           "độ sáng trung bình: " + ", ".join("?" if x is None else f"{x:.0f}" for x in lumas), critical=False)

    passed = all(c["ok"] for c in checks if c["critical"])
    return {"passed": passed, "checks": checks, "info": info}
