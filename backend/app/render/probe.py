"""Media inspection. Uses ffprobe (JSON) when available, otherwise parses `ffmpeg -i` output."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from app.render.ffmpeg import ffprobe_bin, run_capture


class ProbeError(ValueError):
    pass


def _fps(value: str | None) -> float | None:
    if not value or value in ("0/0", "0"):
        return None
    if "/" in value:
        num, den = value.split("/", 1)
        try:
            return float(num) / float(den) if float(den) else None
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_ffprobe_json(data: dict) -> dict:
    fmt = data.get("format") or {}
    info: dict = {
        "format_name": fmt.get("format_name", ""),
        "duration": float(fmt["duration"]) if fmt.get("duration") not in (None, "N/A") else None,
        "size": int(fmt["size"]) if fmt.get("size") else None,
        "video": None,
        "audio": None,
    }
    for st in data.get("streams") or []:
        kind = st.get("codec_type")
        if kind == "video" and info["video"] is None:
            # attached pictures (cover art in mp3) are not real video
            if (st.get("disposition") or {}).get("attached_pic"):
                continue
            info["video"] = {
                "codec": st.get("codec_name"),
                "width": st.get("width"),
                "height": st.get("height"),
                "fps": _fps(st.get("avg_frame_rate")) or _fps(st.get("r_frame_rate")),
                "pix_fmt": st.get("pix_fmt"),
            }
        elif kind == "audio" and info["audio"] is None:
            info["audio"] = {
                "codec": st.get("codec_name"),
                "sample_rate": int(st["sample_rate"]) if st.get("sample_rate") else None,
                "channels": st.get("channels"),
            }
    if info["duration"] is None:
        for st in data.get("streams") or []:
            if st.get("duration") not in (None, "N/A"):
                info["duration"] = float(st["duration"])
                break
    return info


_DUR = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_INPUT = re.compile(r"Input #0,\s*([^,]+(?:,[^,\s]+)*?),\s*from")
_VIDEO = re.compile(r"Stream #0:\d+.*?: Video: (\w+)[^,]*,\s*(\w+)(?:\([^)]*\))?.*?,\s*(\d{2,5})x(\d{2,5})")
_FPS = re.compile(r"(\d+(?:\.\d+)?)\s*fps")
_AUDIO = re.compile(r"Stream #0:\d+.*?: Audio: (\w+)[^,]*,\s*(\d+)\s*Hz,\s*([\w.() ]+?)(?:,|$)")


def parse_ffmpeg_stderr(text: str) -> dict:
    info: dict = {"format_name": "", "duration": None, "size": None, "video": None, "audio": None}
    m = _INPUT.search(text)
    if m:
        info["format_name"] = m.group(1).strip()
    m = _DUR.search(text)
    if m:
        h, mi, s = m.groups()
        info["duration"] = int(h) * 3600 + int(mi) * 60 + float(s)
    for line in text.splitlines():
        if info["video"] is None and " Video: " in line and "attached pic" not in line:
            vm = _VIDEO.search(line)
            if vm:
                fm = _FPS.search(line)
                info["video"] = {
                    "codec": vm.group(1), "pix_fmt": vm.group(2),
                    "width": int(vm.group(3)), "height": int(vm.group(4)),
                    "fps": float(fm.group(1)) if fm else None,
                }
        if info["audio"] is None and " Audio: " in line:
            am = _AUDIO.search(line)
            if am:
                layout = am.group(3).strip()
                channels = {"mono": 1, "stereo": 2}.get(layout.split("(")[0].strip())
                if channels is None:
                    cm = re.match(r"(\d+)\s*channels", layout)
                    channels = int(cm.group(1)) if cm else None
                    if channels is None and "5.1" in layout:
                        channels = 6
                info["audio"] = {"codec": am.group(1), "sample_rate": int(am.group(2)), "channels": channels}
    return info


def probe(path: Path | str) -> dict:
    """Return {format_name, duration, size, video{codec,width,height,fps,pix_fmt}, audio{codec,sample_rate,channels}}."""
    path = Path(path)
    if not path.exists():
        raise ProbeError(f"File không tồn tại: {path.name}")
    exe = ffprobe_bin()
    if exe:
        out = subprocess.run(
            [exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        if out.returncode != 0:
            raise ProbeError(f"Không đọc được media: {out.stderr.strip()[:300]}")
        info = parse_ffprobe_json(json.loads(out.stdout or "{}"))
    else:
        out = run_capture(["-i", str(path)], timeout=120)  # exits 1 ("no output file"), that's expected
        if "Invalid data found" in out.stderr or "Input #0" not in out.stderr:
            raise ProbeError("Không đọc được media (định dạng không hỗ trợ hoặc file hỏng)")
        info = parse_ffmpeg_stderr(out.stderr)
    info["size"] = info.get("size") or path.stat().st_size
    return info
