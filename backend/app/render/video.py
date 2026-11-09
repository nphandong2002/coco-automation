"""Video filtergraph builders.

Rendering strategy (fast & low-memory on an 8 GB PC):
  1. BASE LOOP — render `loop_seconds` of animation once. Every motion is periodic with
     a period dividing the loop length, so the last frame flows into the first (seamless).
  2. FINAL —
       * no time-dependent overlay → loop the base clip with stream copy (no re-encode,
         an 8-hour video is assembled in minutes);
       * Pomodoro / countdown timer → loop the base clip as input and re-encode once with
         drawtext overlays (one heavy pass, CPU-bound, memory stays small).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from app.render.fonts import escape_filter_path, quote_option
from app.render.timeline import FOCUS, SESSION, Phase

BACKGROUND_MOTIONS = {
    "static": "Tĩnh",
    "slow_zoom": "Zoom chậm (vào/ra)",
    "pan": "Lia ngang chậm",
}
EFFECTS = {
    "rain": "Hạt mưa rơi",
    "snow": "Tuyết rơi",
    "warm_flicker": "Ánh sáng ấm lập lòe (lửa/nến)",
    "vignette": "Viền tối (vignette)",
    "film_grain": "Hạt phim",
}
CHARACTER_MOTIONS = {"none": "Đứng yên", "bob": "Nhún nhẹ lên xuống", "sway": "Lắc nhẹ trái phải"}
CHARACTER_POSITIONS = ("bottom_right", "bottom_left", "bottom_center", "center", "right", "left")
OVERLAY_MODES = {"none": "Không", "pomodoro": "Đồng hồ Pomodoro", "countdown": "Đếm ngược tổng"}
OVERLAY_POSITIONS = ("top_center", "top_left", "top_right", "bottom_center", "center")

ZOOM_AMOUNT = 0.06
PAN_EXTRA = 1.12


def background_scale(motion: str) -> float:
    """How much larger than the output the prepared background must be."""
    # 1.5x keeps zoompan's integer-pixel steps invisible while staying ~2.5x faster than 2x
    return {"slow_zoom": 1.5, "pan": PAN_EXTRA}.get(motion, 1.0)


def _cycles(loop: float, target_period: float) -> int:
    """Integer number of cycles per loop closest to the wanted period (seamless loop)."""
    return max(1, round(loop / target_period))


@dataclass
class CharacterSpec:
    path: Path
    width: int
    height: int
    position: str = "bottom_right"
    motion: str = "bob"


@dataclass
class BaseLoopSpec:
    width: int
    height: int
    fps: int
    loop_seconds: float
    background: Path
    motion: str = "slow_zoom"
    effects: list[str] = field(default_factory=list)
    character: CharacterSpec | None = None
    textures: dict[str, Path] = field(default_factory=dict)   # effect name -> png


def _char_xy(spec: CharacterSpec, W: int, H: int) -> tuple[int, int]:
    margin_x, margin_y = int(W * 0.04), int(H * 0.03)
    w, h = spec.width, spec.height
    pos = spec.position
    x = {"bottom_left": margin_x, "left": margin_x,
         "bottom_center": (W - w) // 2, "center": (W - w) // 2}.get(pos, W - w - margin_x)
    y = (H - h) // 2 if pos in ("center", "left", "right") else H - h - margin_y
    return x, y


def build_base_loop(spec: BaseLoopSpec, output: Path, *, crf: int, preset: str,
                    max_bitrate_kbps: int, threads: int) -> list[str]:
    W, H, fps, L = spec.width, spec.height, spec.fps, float(spec.loop_seconds)
    frames = int(round(L * fps))
    args: list[str] = ["-loop", "1", "-framerate", str(fps), "-i", str(spec.background)]
    next_input = 1
    stmts: list[str] = []

    # 1. background motion
    if spec.motion == "slow_zoom":
        z = f"1+{ZOOM_AMOUNT}*(1-cos(2*PI*on/{frames}))/2"
        stmts.append(
            f"[0:v]zoompan=z={quote_option(z)}:x={quote_option('iw/2-(iw/zoom/2)')}"
            f":y={quote_option('ih/2-(ih/zoom/2)')}:d=1:s={W}x{H}:fps={fps},setsar=1,format=yuv420p[bg0]"
        )
    elif spec.motion == "pan":
        x = f"(iw-ow)*(1-cos(2*PI*t/{L:g}))/2"
        stmts.append(f"[0:v]crop={W}:{H}:x={quote_option(x)}:y={quote_option('(ih-oh)/2')},"
                     f"setsar=1,format=yuv420p[bg0]")
    else:
        stmts.append(f"[0:v]scale={W}:{H},setsar=1,format=yuv420p[bg0]")
    cur = "bg0"

    # 2. particles (behind the character: rain/snow seen through the window)
    for eff in ("rain", "snow"):
        if eff not in spec.effects or eff not in spec.textures:
            continue
        args += ["-loop", "1", "-framerate", str(fps), "-i", str(spec.textures[eff])]
        idx = next_input
        next_input += 1
        speed_target = 900.0 if eff == "rain" else 70.0          # px/s at 1080p
        k = _cycles(L, H / (speed_target * H / 1080))
        v = H * k / L
        if eff == "rain":
            x_expr = "0"
        else:  # snow drifts sideways (texture is wider than the frame)
            ks = _cycles(L, 6.0)
            x_expr = f"-24+18*sin(2*PI*t*{ks}/{L:g})"
        # two copies of the tileable texture, stacked by position (cheaper than vstack)
        y1 = f"mod(t*{v:.6f},{H})-{H}"
        y2 = f"mod(t*{v:.6f},{H})"
        stmts.append(f"[{idx}:v]format=yuva420p,split[{eff}a][{eff}b]")
        stmts.append(f"[{cur}][{eff}a]overlay=x={quote_option(x_expr)}:y={quote_option(y1)}"
                     f":eval=frame:format=yuv420[{eff}o1]")
        stmts.append(f"[{eff}o1][{eff}b]overlay=x={quote_option(x_expr)}:y={quote_option(y2)}"
                     f":eval=frame:format=yuv420[{eff}o]")
        cur = f"{eff}o"

    # 3. character (pinned version image)
    if spec.character is not None:
        c = spec.character
        args += ["-loop", "1", "-framerate", str(fps), "-i", str(c.path)]
        idx = next_input
        next_input += 1
        x0, y0 = _char_xy(c, W, H)
        kb = _cycles(L, 4.0)
        xs, ys = str(x0), str(y0)
        if c.motion == "bob":
            ys = f"{y0}+{max(2, H // 180)}*sin(2*PI*t*{kb}/{L:g})"
        elif c.motion == "sway":
            xs = f"{x0}+{max(2, W // 240)}*sin(2*PI*t*{kb}/{L:g})"
        stmts.append(f"[{idx}:v]format=yuva420p[chr]")
        stmts.append(f"[{cur}][chr]overlay=x={quote_option(xs)}:y={quote_option(ys)}:eval=frame:format=yuv420[co]")
        cur = "co"

    # 4. global looks
    post: list[str] = []
    if "warm_flicker" in spec.effects:
        k1, k2, k3 = _cycles(L, 1 / 1.3), _cycles(L, 1 / 3.1), _cycles(L, 1 / 7.3)
        b = (f"0.014*sin(2*PI*t*{k1}/{L:g})+0.009*sin(2*PI*t*{k2}/{L:g}+1.7)"
             f"+0.005*sin(2*PI*t*{k3}/{L:g}+0.4)")
        post.append(f"eq=brightness={quote_option(b)}:eval=frame")
    if "vignette" in spec.effects:
        post.append("vignette=angle=PI/5")
    if "film_grain" in spec.effects:
        post.append("noise=alls=6:allf=t")
    post.append("format=yuv420p")
    stmts.append(f"[{cur}]{','.join(post)}[vout]")

    args += ["-filter_complex", ";".join(stmts), "-map", "[vout]", "-frames:v", str(frames),
             "-r", str(fps), *x264_args(fps, crf, preset, max_bitrate_kbps, threads), "-an", str(output)]
    return args


def x264_args(fps: int, crf: int, preset: str, max_bitrate_kbps: int, threads: int) -> list[str]:
    gop = fps * 2
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-maxrate", f"{max_bitrate_kbps}k", "-bufsize", f"{max_bitrate_kbps * 2}k",
            "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-threads", str(threads)]


# ------------------------------------------------------------------ timer overlay
@dataclass
class OverlaySpec:
    mode: str                       # pomodoro | countdown
    phases: list[Phase]
    font: Path
    labels: dict[str, str]
    position: str = "top_center"
    color: str = "#FFFFFF"
    box: bool = True


def _remaining(end: float) -> str:
    return f"ceil({end:.3f}-t)"


def _timer_text(end: float, with_hours: bool) -> str:
    r = _remaining(end)
    mm = f"%{{eif:mod(floor({r}/60),60):d:2}}" if with_hours else f"%{{eif:floor({r}/60):d:2}}"
    ss = f"%{{eif:mod({r},60):d:2}}"
    if with_hours:
        return f"%{{eif:floor({r}/3600):d}}:{mm}:{ss}"
    return f"{mm}:{ss}"


def _clean_label(s: str) -> str:
    return s.replace("%", "").replace("\n", " ")[:60]


def overlay_filters(spec: OverlaySpec, W: int, H: int) -> list[str]:
    """drawtext filters (comma-joined chain) for every phase of the timeline."""
    font = escape_filter_path(spec.font)
    color = spec.color.lstrip("#")
    fs_timer = int(H * 0.11)
    fs_label = int(H * 0.034)
    pos = spec.position
    if pos == "top_left":
        x = quote_option(f"{int(W * 0.05)}")
    elif pos == "top_right":
        x = quote_option(f"w-text_w-{int(W * 0.05)}")
    else:
        x = quote_option("(w-text_w)/2")
    if pos.startswith("top"):
        y_label = int(H * 0.06)
    elif pos == "bottom_center":
        y_label = H - int(H * 0.10) - fs_timer - int(fs_label * 1.5)
    else:
        y_label = (H - fs_timer) // 2 - int(fs_label * 1.5)
    y_timer = y_label + int(fs_label * 1.5)
    common = (f"fontfile={font}:fontcolor=0x{color}:shadowcolor=black@0.55:shadowx=3:shadowy=3")
    box = ":box=1:boxcolor=black@0.28:boxborderw=22" if spec.box else ""
    out: list[str] = []
    for p in spec.phases:
        enable = quote_option(f"gte(t,{p.start:.3f})*lt(t,{p.end:.3f})")
        label = spec.labels.get(p.kind, p.kind.upper())
        if p.kind == FOCUS and spec.mode == "pomodoro":
            label = f"{label}  {p.index}/{p.total}"
        with_hours = p.kind == SESSION and p.duration >= 3600
        out.append(f"drawtext={common}:text={quote_option(_clean_label(label))}:fontsize={fs_label}"
                   f":x={x}:y={y_label}:enable={enable}")
        out.append(f"drawtext={common}{box}:text={quote_option(_timer_text(p.end, with_hours))}"
                   f":fontsize={fs_timer}:x={x}:y={y_timer}:enable={enable}")
    return out


def build_final(base: Path, audio: Path, output: Path, duration: float, *,
                overlay: OverlaySpec | None, width: int, height: int, fps: int, crf: int,
                preset: str, max_bitrate_kbps: int, threads: int) -> tuple[list[str], str | None]:
    """Return (args, filtergraph or None). With a filtergraph, the caller passes it via
    ffmpeg.filter_complex_args() (it can be long) and maps [vout]."""
    inputs = ["-stream_loop", "-1", "-i", str(base), "-i", str(audio)]
    tail = ["-t", f"{duration:.3f}", "-movflags", "+faststart", str(output)]
    if overlay is None or overlay.mode == "none" or not overlay.phases:
        return [*inputs, "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", *tail], None
    graph = "[0:v]" + ",".join(overlay_filters(overlay, width, height)) + ",format=yuv420p[vout]"
    out = ["-map", "[vout]", "-map", "1:a:0", "-r", str(fps),
           *x264_args(fps, crf, preset, max_bitrate_kbps, threads), "-c:a", "copy", *tail]
    return inputs + ["__FILTER__"] + out, graph


def estimate_size_bytes(duration: float, max_bitrate_kbps: int, audio_kbps: int) -> int:
    """Upper bound of the output size (CRF + maxrate cap) used for the free-disk check."""
    return int(math.ceil(duration * (max_bitrate_kbps + audio_kbps) * 1000 / 8))
