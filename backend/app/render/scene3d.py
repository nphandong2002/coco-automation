"""3D scene -> seamless loop video.

The dashboard's three.js engine (frontend `capture.html`) is opened in headless Chromium and driven
frame by frame; every JPEG frame is piped straight into FFmpeg (no frames kept on disk, small RAM).
No GPU is required: Chromium falls back to software WebGL (SwiftShader).

Needs: Chromium/Chrome/Edge (CHROMIUM_PATH or auto-detected), the `playwright` pip package (used only as
a driver — no browser download), and the built frontend (`frontend/dist/capture.html`).
"""
from __future__ import annotations

import base64
import functools
import http.server
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from app.core import storage
from app.core.config import get_settings
from app.render import ffmpeg as ff
from app.render.video import x264_args

log = logging.getLogger("coco.render.scene3d")


class Scene3DError(ff.FFmpegError):
    """Capture failed (browser/WebGL/page problem). Subclass of FFmpegError so the worker retries once."""


_WINDOWS_BROWSERS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)
_NAMES = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "microsoft-edge", "chrome")


def find_chromium() -> str | None:
    configured = get_settings().chromium_path
    if configured:
        return configured if Path(configured).exists() else None
    for name in _NAMES:
        found = shutil.which(name)
        if found:
            return found
    # Chromium installed by `python -m playwright install chromium`
    roots = [Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])] if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") else []
    roots += [Path.home() / ".cache" / "ms-playwright", Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"]
    for root in roots:
        for pattern in ("chromium-*/chrome-linux/chrome", "chromium-*/chrome-win/chrome.exe"):
            hits = sorted(root.glob(pattern)) if root.is_dir() else []
            if hits:
                return str(hits[-1])
    if sys.platform == "win32":
        for p in _WINDOWS_BROWSERS:
            if Path(p).exists():
                return p
    return None


def status() -> dict:
    """What the dashboard shows: can 3D scenes be rendered on this machine, and if not, why."""
    exe = find_chromium()
    try:
        import playwright  # noqa: F401
        has_pw = True
    except ImportError:
        has_pw = False
    dist = get_settings().frontend_dist
    built = (dist / "capture.html").exists()
    reason = None
    if exe is None:
        reason = ("Không tìm thấy Chromium/Chrome. Cài: sudo apt install chromium "
                  "(hoặc đặt CHROMIUM_PATH trong .env)")
    elif not has_pw:
        reason = "Thiếu gói Python 'playwright'. Chạy: .venv/bin/pip install -r backend/requirements.txt"
    elif not built:
        reason = "Frontend chưa build (thiếu capture.html). Chạy: cd frontend && npm ci && npm run build"
    return {"available": reason is None, "chromium": exe, "playwright": has_pw, "frontend_built": built,
            "reason": reason}


def require() -> str:
    st = status()
    if not st["available"]:
        raise Scene3DError(st["reason"])
    return st["chromium"]


# ---------------------------------------------------------------- local static server (127.0.0.1 only)
class _Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript",
                      ".mjs": "text/javascript", ".glb": "model/gltf-binary", ".css": "text/css",
                      ".html": "text/html"}

    def __init__(self, *a, dist: str, **kw):  # noqa: ANN002, ANN003
        self._dist = dist
        super().__init__(*a, directory=dist, **kw)

    def translate_path(self, path: str) -> str:
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith("/media/"):
            try:  # storage.resolve refuses anything outside the storage root
                return str(storage.resolve(path.removeprefix("/media/")))
            except storage.StorageError:
                return str(Path(self._dist) / "__forbidden__")
        return super().translate_path(path)

    def log_message(self, *a) -> None:  # noqa: ANN002
        pass


def _serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(_Handler, dist=str(get_settings().frontend_dist))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True, name="scene3d-http").start()
    return srv, srv.server_address[1]


def _browser_args() -> list[str]:
    args = ["--disable-dev-shm-usage", "--hide-scrollbars", "--mute-audio", "--no-first-run",
            "--disable-extensions", "--autoplay-policy=no-user-gesture-required"]
    if get_settings().scene3d_software_gl:
        args += ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        args.append("--no-sandbox")   # Chromium refuses to start as root otherwise
    return args


# ---------------------------------------------------------------- capture
def capture_loop(*, scene: dict, model_rel: str | None, width: int, height: int, capture_fps: int, out_fps: int,
                 loop_seconds: float, output: Path, still_path: Path, crf: int, preset: str, max_bitrate_kbps: int,
                 threads: int, on_progress: Callable[[float], None] | None = None,
                 should_cancel: Callable[[], bool] | None = None, timeout: float | None = None,
                 log_file: Path | None = None, event: dict | None = None, reserve_event: bool = False,
                 exact_loop: bool = False) -> float:
    """Render `scene` into `output` (H.264, `out_fps`, seamless loop). Returns the real loop length (s).

    reserve_event: make the loop long enough to hold a break_time reaction (base loop of a video that has breaks).
    event / exact_loop: render the *variant* loop in which the reaction plays once; it has exactly the base
    loop's length and starts/ends in the same pose, so it can replace one repetition of the base loop.
    """
    exe = require()
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import sync_playwright

    started = time.monotonic()
    output.parent.mkdir(parents=True, exist_ok=True)
    log_fh = log_file.open("a", encoding="utf-8") if log_file else None

    def note(msg: str) -> None:
        if log_fh:
            log_fh.write(msg + "\n")
            log_fh.flush()

    srv, port = _serve()
    proc: subprocess.Popen | None = None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=exe, headless=True, args=_browser_args())
            try:
                page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
                page.on("pageerror", lambda e: note(f"[page error] {e}"))
                page.on("console", lambda m: note(f"[console.{m.type}] {m.text}") if m.type in ("error", "warning") else None)
                page.goto(f"http://127.0.0.1:{port}/capture.html", wait_until="load", timeout=30_000)
                page.wait_for_function("window.__coco3dReady === true", timeout=30_000)
                model_url = f"http://127.0.0.1:{port}/media/{model_rel}" if model_rel else None
                try:
                    info = page.evaluate("o => window.coco3d.init(o)", {
                        "scene": scene, "modelUrl": model_url, "width": width, "height": height,
                        "loopSeconds": loop_seconds, "reserveEvent": reserve_event, "exactLoop": exact_loop,
                        "event": event})
                except PWError as exc:
                    raise Scene3DError(f"Không khởi tạo được cảnh 3D (WebGL?): {str(exc)[:300]}") from exc
                if event and not info.get("eventFits"):
                    raise Scene3DError("Vòng lặp quá ngắn để chứa phản ứng giờ nghỉ của nhân vật")
                L = float(info["loopSeconds"])
                n = max(2, round(L * capture_fps))
                dt = L / n                       # exact: frame n == frame 0, so the loop has no seam
                note(f"3D loop{' (variant: ' + event['name'] + ')' if event else ''}: {L:.2f}s, {n} frames @ {capture_fps} fps "
                     f"-> {out_fps} fps, placeholder={info['placeholder']}, clips={info['clips']}")

                cmd = [ff.ffmpeg_bin(), "-hide_banner", "-y", "-loglevel", "error",
                       "-f", "image2pipe", "-framerate", f"{n / L:.6f}", "-c:v", "mjpeg", "-i", "-",
                       "-vf", f"fps={out_fps},scale=in_range=full:out_range=limited,format=yuv420p", "-an",
                       *x264_args(out_fps, crf, preset, max_bitrate_kbps, threads), str(output)]
                note("$ " + " ".join(cmd))
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                        stderr=log_fh or subprocess.DEVNULL,
                                        **ff._priority_kwargs(get_settings().render_nice))
                still_at = n // 3
                for i in range(n):
                    if should_cancel is not None and should_cancel():
                        raise ff.RenderCancelled("Đã hủy")
                    if timeout is not None and time.monotonic() - started > timeout:
                        raise ff.RenderTimeout(f"Quá thời gian chụp cảnh 3D ({int(timeout)} s)")
                    try:
                        b64 = page.evaluate("([dt, first]) => window.coco3d.frame(dt, first)", [dt, i == 0])
                    except PWError as exc:
                        raise Scene3DError(f"Chromium lỗi ở khung hình {i}/{n}: {str(exc)[:300]}") from exc
                    data = base64.b64decode(b64)
                    if i == still_at:
                        still_path.write_bytes(data)
                    try:
                        proc.stdin.write(data)  # type: ignore[union-attr]
                    except (BrokenPipeError, OSError) as exc:
                        raise Scene3DError("FFmpeg dừng giữa chừng khi nhận khung hình 3D") from exc
                    if on_progress and i % 5 == 0:
                        on_progress(i / n)
                proc.stdin.close()  # type: ignore[union-attr]
                code = proc.wait(timeout=300)
                if code != 0:
                    raise Scene3DError(f"FFmpeg mã hóa vòng lặp 3D thất bại (exit {code})")
                proc = None
                if on_progress:
                    on_progress(1.0)
                return L
            except PWError as exc:
                raise Scene3DError(f"Lỗi trình duyệt khi chụp cảnh 3D: {str(exc)[:300]}") from exc
            finally:
                try:
                    browser.close()
                except Exception:  # noqa: BLE001
                    pass
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=15)
        srv.shutdown()
        srv.server_close()
        if log_fh:
            log_fh.write(f"===== 3d-capture finished in {time.monotonic() - started:.1f}s\n")
            log_fh.close()
