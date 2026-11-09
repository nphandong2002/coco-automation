"""Locate and run FFmpeg safely.

* progress is read from `-progress pipe:1` (out_time) and reported as a 0..1 fraction
* the process runs with a lower CPU priority (nice on Linux) and a thread limit
* cancellation and timeout terminate the process (SIGTERM, then SIGKILL)
* stderr goes to a per-job log file; the tail is included in the error message
"""
from __future__ import annotations

import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

log = logging.getLogger("coco.render.ffmpeg")

ProgressFn = Callable[[float], None]
CancelFn = Callable[[], bool]


class FFmpegNotFound(RuntimeError):
    pass


class FFmpegError(RuntimeError):
    pass


class RenderCancelled(Exception):
    pass


class RenderTimeout(RuntimeError):
    pass


def ffmpeg_bin() -> str:
    configured = get_settings().ffmpeg_path.strip()
    path = configured or shutil.which("ffmpeg")
    if not path or not Path(path).exists() and not shutil.which(path):
        raise FFmpegNotFound(
            "Không tìm thấy FFmpeg. Trên Ubuntu: sudo apt install ffmpeg (hoặc đặt FFMPEG_PATH trong .env)"
        )
    return path


def ffprobe_bin() -> str | None:
    configured = get_settings().ffprobe_path.strip()
    if configured:
        return configured if Path(configured).exists() or shutil.which(configured) else None
    found = shutil.which("ffprobe")
    if found:
        return found
    # ffprobe usually sits next to ffmpeg
    try:
        sibling = Path(ffmpeg_bin()).with_name("ffprobe" + (".exe" if sys.platform == "win32" else ""))
        return str(sibling) if sibling.exists() else None
    except FFmpegNotFound:
        return None


@lru_cache
def ffmpeg_version(path: str | None = None) -> tuple[int, int, str]:
    """(major, minor, full version string). Unknown builds (git snapshots) → (99, 0, ...)."""
    exe = path or ffmpeg_bin()
    out = subprocess.run([exe, "-hide_banner", "-version"], capture_output=True, text=True, timeout=20)
    first = (out.stdout or out.stderr).splitlines()[0] if (out.stdout or out.stderr) else ""
    m = re.search(r"version\s+n?(\d+)\.(\d+)", first)
    if m:
        return int(m.group(1)), int(m.group(2)), first
    return 99, 0, first


@lru_cache
def has_filter(name: str, path: str | None = None) -> bool:
    exe = path or ffmpeg_bin()
    out = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20)
    return re.search(rf"^\s*\S+\s+{re.escape(name)}\s", out.stdout, re.MULTILINE) is not None


def render_threads() -> int:
    n = get_settings().render_threads
    if n > 0:
        return n
    return max(1, (os.cpu_count() or 2) - 1)


def filter_complex_args(graph: str, workdir: Path, name: str = "graph") -> list[str]:
    """Pass a filtergraph inline, or through a file when it is long (command-line limits)."""
    if len(graph) < 8000:
        return ["-filter_complex", graph]
    script = workdir / f"{name}.filtergraph"
    script.write_text(graph, encoding="utf-8")
    major, _, _ = ffmpeg_version()
    if major >= 7:
        return ["-/filter_complex", str(script)]
    return ["-filter_complex_script", str(script)]


def _priority_kwargs(nice: int) -> dict:
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)}
    if nice <= 0:
        return {}

    def _lower_priority() -> None:  # runs in the child before exec
        try:
            os.nice(nice)
        except OSError:
            pass

    return {"preexec_fn": _lower_priority}


def _tail(path: Path | None, lines: int = 25) -> str:
    if path is None or not path.exists():
        return ""
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 16000))
            data = fh.read().decode("utf-8", errors="replace")
        return "\n".join(data.strip().splitlines()[-lines:])
    except OSError:
        return ""


def run(
    args: list[str],
    *,
    duration: float | None = None,
    on_progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
    timeout: float | None = None,
    log_file: Path | None = None,
    label: str = "ffmpeg",
) -> None:
    """Run ffmpeg with `args` (without the binary). Raises FFmpegError / RenderCancelled / RenderTimeout."""
    settings = get_settings()
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
           "-progress", "pipe:1", "-nostats", *args]
    log_fh = None
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_fh = log_file.open("a", encoding="utf-8")
        log_fh.write(f"\n===== {label} @ {time.strftime('%Y-%m-%d %H:%M:%S')}\n$ {' '.join(cmd)}\n")
        log_fh.flush()

    started = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=log_fh if log_fh else subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        **_priority_kwargs(settings.render_nice),
    )
    lines: queue.Queue[str | None] = queue.Queue()

    def _reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=_reader, daemon=True, name=f"{label}-progress").start()

    def _stop(reason: str) -> None:
        log.warning("Stopping %s: %s", label, reason)
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=15)

    try:
        eof = False
        while True:
            try:
                line = lines.get(timeout=1.0)
            except queue.Empty:
                line = ""
            if line is None:
                eof = True
            elif line.startswith(("out_time_us=", "out_time_ms=")) and duration and on_progress:
                try:
                    us = int(line.split("=", 1)[1].strip())
                    on_progress(max(0.0, min(1.0, us / 1_000_000 / duration)))
                except ValueError:
                    pass
            if should_cancel is not None and should_cancel():
                _stop("cancel requested")
                raise RenderCancelled(f"{label}: đã hủy")
            if timeout is not None and time.monotonic() - started > timeout:
                _stop("timeout")
                raise RenderTimeout(f"{label}: quá thời gian cho phép ({int(timeout)} s)")
            if eof:
                break
        code = proc.wait()
        if code != 0:
            raise FFmpegError(f"{label} thất bại (exit {code}). {_tail(log_file)}".strip())
        if on_progress:
            on_progress(1.0)
    finally:
        if proc.poll() is None:
            proc.kill()
        if log_fh:
            log_fh.write(f"===== {label} finished in {time.monotonic() - started:.1f}s\n")
            log_fh.close()


def run_capture(args: list[str], timeout: float = 120) -> subprocess.CompletedProcess:
    """Short helper commands (probe, analysis). Output captured, no progress."""
    return subprocess.run([ffmpeg_bin(), "-hide_banner", "-nostdin", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)
