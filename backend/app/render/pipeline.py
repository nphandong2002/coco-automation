"""Execute a render plan: prepare → base loop → audio → final → thumbnail → QC.

The plan is a JSON dict built by services/render_service.build_plan() and stored in
`video_jobs.render_config`. Paths inside the plan are storage-relative and resolved with
the `resolve` callback (which also blocks path traversal).
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.render import audio, scene, video
from app.render import ffmpeg as ff
from app.render.fonts import find_font
from app.render.qc import check_video
from app.render.thumbnail import render_thumbnail
from app.render.timeline import from_json

log = logging.getLogger("coco.render.pipeline")

ProgressCb = Callable[[float, str], None]


class RenderFailed(RuntimeError):
    def __init__(self, message: str, qc: dict | None = None) -> None:
        super().__init__(message)
        self.qc = qc


@dataclass
class RenderResult:
    video_path: Path
    thumbnail_path: Path | None
    duration: float
    width: int
    height: int
    fps: float
    size_bytes: int
    sha256: str
    qc: dict


def sha256_file(path: Path, chunk: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def render(plan: dict, *, resolve: Callable[[str], Path], workdir: Path, output_dir: Path,
           log_file: Path, on_progress: ProgressCb | None = None,
           should_cancel: Callable[[], bool] | None = None, timeout: float | None = None) -> RenderResult:
    started = time.monotonic()
    W, H, fps = int(plan["width"]), int(plan["height"]), int(plan["fps"])
    D = float(plan["duration_sec"])
    loop = float(min(int(plan.get("loop_seconds", 60)), D))
    vcfg = plan.get("video", {})
    acfg = plan.get("audio", {})
    crf, preset = int(vcfg.get("crf", 22)), str(vcfg.get("preset", "veryfast"))
    max_kbps, abr = int(vcfg.get("max_bitrate_kbps", 4500)), int(acfg.get("bitrate_kbps", 192))
    threads = ff.render_threads()
    overlay_cfg = plan.get("overlay") or {"mode": "none"}
    has_overlay = overlay_cfg.get("mode", "none") != "none" and bool(plan.get("timeline"))

    weights = {"prepare": 0.03, "base": 0.17, "audio": 0.15,
               "final": 0.55 if has_overlay else 0.05, "thumbnail": 0.02, "qc": 0.08}
    total_w = sum(weights.values())
    order = list(weights)

    def report(step: str, frac: float) -> None:
        if on_progress is None:
            return
        done = sum(weights[s] for s in order[: order.index(step)])
        on_progress(min(0.999, (done + weights[step] * frac) / total_w), step)

    def remaining() -> float | None:
        if timeout is None:
            return None
        left = timeout - (time.monotonic() - started)
        if left <= 0:
            raise ff.RenderTimeout(f"Quá thời gian render cho phép ({int(timeout)} s)")
        return left

    def check_cancel() -> None:
        if should_cancel is not None and should_cancel():
            raise ff.RenderCancelled("Đã hủy")

    workdir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- 1. prepare
    report("prepare", 0)
    bg_cfg = plan["background"]
    motion = bg_cfg.get("motion", "slow_zoom")
    scale = video.background_scale(motion)
    bg_src = resolve(bg_cfg["path"])
    bg = scene.prepare_background(bg_src, workdir / "bg.png", _even(W * scale), _even(H * scale))
    char_spec = None
    char_src: Path | None = None
    if plan.get("character") and plan["character"].get("path"):
        c = plan["character"]
        char_src = resolve(c["path"])
        cpath, cw, ch = scene.prepare_character(char_src, workdir / "character.png",
                                                _even(H * float(c.get("scale", 0.42))))
        char_spec = video.CharacterSpec(cpath, cw, ch, c.get("position", "bottom_right"), c.get("motion", "bob"))
    effects = list(plan.get("effects") or [])
    textures: dict[str, Path] = {}
    seed = int(plan.get("seed", 1))
    if "rain" in effects:
        textures["rain"] = scene.rain_texture(workdir / "rain.png", W, H, seed=seed)
    if "snow" in effects:
        textures["snow"] = scene.snow_texture(workdir / "snow.png", W + 48, H, seed=seed)
    font: Path | None = None
    if has_overlay or (plan.get("thumbnail") or {}).get("generate"):
        font = resolve(overlay_cfg["font_path"]) if overlay_cfg.get("font_path") else find_font()
        if has_overlay and font is None:
            raise RenderFailed("Không tìm thấy font cho đồng hồ. Cài: sudo apt install fonts-dejavu-core "
                               "hoặc đặt FONT_PATH / chọn font asset")
    check_cancel()
    report("prepare", 1)

    # ---------------------------------------------------------------- 2. base loop
    base_path = workdir / "base.mp4"
    spec = video.BaseLoopSpec(W, H, fps, loop, bg, motion, effects, char_spec, textures)
    ff.run(video.build_base_loop(spec, base_path, crf=crf, preset=preset, max_bitrate_kbps=max_kbps,
                                 threads=threads),
           duration=loop, on_progress=lambda f: report("base", f), should_cancel=should_cancel,
           timeout=remaining(), log_file=log_file, label="base-loop")

    # ---------------------------------------------------------------- 3. audio
    audio_path = workdir / "audio.m4a"
    layers = []
    for i, l in enumerate(plan.get("layers") or []):
        if l["kind"] == "asset":
            layers.append(audio.AudioLayer("asset", float(l.get("volume", 1)), path=resolve(l["path"])))
        else:
            layers.append(audio.AudioLayer("generator", float(l.get("volume", 1)), generator=l["generator"],
                                           seed=int(l.get("seed", seed + i))))
    phases = from_json(plan.get("timeline") or [])
    transitions = [p.start for p in phases[1:]] if plan.get("chime") else []
    inputs, graph = audio.build_audio_command(
        layers, D, audio_path, transitions=transitions, chime_volume=float(acfg.get("chime_volume", 0.6)),
        master_volume=float(acfg.get("master_volume", 1.0)), fade_in=float(acfg.get("fade_in", 3)),
        fade_out=float(acfg.get("fade_out", 5)), bitrate_kbps=abr)
    ff.run([*inputs, *ff.filter_complex_args(graph, workdir, "audio"),
            *audio.audio_output_args(audio_path, D, abr)],
           duration=D, on_progress=lambda f: report("audio", f), should_cancel=should_cancel,
           timeout=remaining(), log_file=log_file, label="audio")

    # ---------------------------------------------------------------- 4. final
    tmp_out = workdir / "video.mp4"
    overlay = None
    if has_overlay and font is not None:
        overlay = video.OverlaySpec(mode=overlay_cfg["mode"], phases=phases, font=font,
                                    labels=overlay_cfg.get("labels") or {},
                                    position=overlay_cfg.get("position", "top_center"),
                                    color=overlay_cfg.get("color", "#FFFFFF"), box=bool(overlay_cfg.get("box", True)))
    args, fgraph = video.build_final(base_path, audio_path, tmp_out, D, overlay=overlay, width=W, height=H,
                                     fps=fps, crf=crf, preset=preset, max_bitrate_kbps=max_kbps, threads=threads)
    if fgraph is not None:
        i = args.index("__FILTER__")
        args = args[:i] + ff.filter_complex_args(fgraph, workdir, "final") + args[i + 1:]
    ff.run(args, duration=D, on_progress=lambda f: report("final", f), should_cancel=should_cancel,
           timeout=remaining(), log_file=log_file, label="final")

    # ---------------------------------------------------------------- 5. thumbnail
    report("thumbnail", 0)
    thumb_cfg = plan.get("thumbnail") or {}
    thumb_tmp: Path | None = None
    if thumb_cfg.get("custom_path"):
        src = resolve(thumb_cfg["custom_path"])
        thumb_tmp = workdir / ("thumbnail" + src.suffix.lower())
        shutil.copyfile(src, thumb_tmp)
    elif thumb_cfg.get("generate", True):
        thumb_tmp = render_thumbnail(workdir / "thumbnail.jpg", background=bg_src,
                                     title=thumb_cfg.get("title_text") or plan.get("title", ""),
                                     badge=thumb_cfg.get("badge", ""), character=char_src,
                                     accent=thumb_cfg.get("accent", "#E3A86B"), font_path=font)
    check_cancel()

    # ---------------------------------------------------------------- 6. QC
    report("qc", 0)
    qc = check_video(tmp_out, width=W, height=H, fps=fps, duration=D)
    qc["render_seconds"] = round(time.monotonic() - started, 1)
    if not qc["passed"]:
        failed = ", ".join(c["name"] for c in qc["checks"] if c["critical"] and not c["ok"])
        raise RenderFailed(f"Kiểm tra chất lượng thất bại: {failed}", qc)

    final_video = output_dir / "video.mp4"
    shutil.move(str(tmp_out), final_video)
    final_thumb = None
    if thumb_tmp is not None:
        final_thumb = output_dir / thumb_tmp.name
        shutil.move(str(thumb_tmp), final_thumb)
    size = final_video.stat().st_size
    digest = sha256_file(final_video)
    report("qc", 1)
    info = qc.get("info") or {}
    return RenderResult(final_video, final_thumb, float(info.get("duration") or D), W, H, float(fps), size,
                        digest, qc)
