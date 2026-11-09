"""FastAPI application entry point.

Run (dev):  uvicorn app.main:app --reload --port 8080   (from backend/)
Run (prod): scripts/start.sh
"""
from __future__ import annotations

import base64
import logging
import secrets

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.routes import assets, channels, characters, content, production, publishing, system, youtube
from app.core.config import get_settings
from app.core.logging_setup import setup_logging
from app.core.security import SecretKeyMissing
from app.core.storage import StorageError, storage_root
from app.render.ffmpeg import FFmpegNotFound
from app.services.errors import AppError

setup_logging()
log = logging.getLogger("coco")
settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version,
              docs_url="/api/docs", openapi_url="/api/openapi.json")


# ------------------------------------------------------------------ auth
@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """Optional HTTP Basic auth for the whole dashboard (set DASHBOARD_PASSWORD)."""
    if settings.dashboard_password and request.url.path != "/api/health":
        header = request.headers.get("authorization", "")
        ok = False
        if header.lower().startswith("basic "):
            try:
                user, _, pwd = base64.b64decode(header[6:]).decode().partition(":")
                ok = secrets.compare_digest(user, settings.dashboard_username) and \
                    secrets.compare_digest(pwd, settings.dashboard_password)
            except Exception:
                ok = False
        if not ok:
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Coco"'})
    return await call_next(request)


# ------------------------------------------------------------------ errors
@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(StorageError)
async def storage_error_handler(_: Request, exc: StorageError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(FFmpegNotFound)
async def ffmpeg_missing_handler(_: Request, exc: FFmpegNotFound):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(SecretKeyMissing)
async def secret_missing_handler(_: Request, exc: SecretKeyMissing):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    msgs = []
    for e in exc.errors():
        loc = ".".join(str(p) for p in e.get("loc", []) if p not in ("body", "query", "path"))
        msg = str(e.get("msg", "")).removeprefix("Value error, ")
        msgs.append(f"{loc}: {msg}" if loc else msg)
    return JSONResponse(status_code=422, content={"detail": "; ".join(msgs)})


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Lỗi hệ thống, xem logs/app.log"})


# ------------------------------------------------------------------ routes
for r in (system.router, channels.router, characters.router, assets.router, content.router,
          production.router, youtube.router, publishing.router):
    app.include_router(r, prefix="/api")

app.mount("/media", StaticFiles(directory=str(storage_root())), name="media")

_dist = settings.frontend_dist
if (_dist / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        """Serve the React SPA (client-side routing)."""
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        candidate = (_dist / full_path).resolve()
        if full_path and candidate.is_file() and _dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")
else:
    @app.get("/", include_in_schema=False)
    async def no_frontend():
        return JSONResponse({"detail": "Frontend chưa được build. Chạy scripts/install.sh hoặc "
                                       "`cd frontend && npm install && npm run build`. API: /api/docs"})
