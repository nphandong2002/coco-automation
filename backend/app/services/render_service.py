"""Render queue (DB side): build render plans, enqueue / cancel / retry jobs, list outputs.

The worker process (app.worker) executes the jobs; see app/worker/runner.py.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import storage
from app.core.config import get_settings
from app.models import Asset, Channel, Character, ContentProject, Video, VideoJob, WorkerStatus
from app.models.enums import (
    DURATION_CHOICES,
    PREVIEW_SECONDS_RANGE,
    JobStatus,
    ProductionStatus,
    VideoJobType,
)
from app.render import ffmpeg as ff
from app.render import scene3d as scene3d_render
from app.schemas.scene3d import Scene3D
from app.render.audio import GENERATORS
from app.render.fonts import find_font
from app.render.metadata import duration_label
from app.render.scene import BACKGROUND_STYLES
from app.render.timeline import DEFAULT_LABELS, countdown_phases, pomodoro_phases, to_json
from app.render.video import (
    BACKGROUND_MOTIONS,
    CHARACTER_MOTIONS,
    CHARACTER_POSITIONS,
    EFFECTS,
    OVERLAY_MODES,
    OVERLAY_POSITIONS,
)
from app.schemas.content import RESOLUTIONS, X264_PRESETS, RenderRequest
from app.schemas.production import Capabilities, JobOut, ProductionStatusOut, VideoOut, WorkerOut
from app.services import activity
from app.services.content_service import character_image, pinned_version, validate_for_render
from app.services.errors import AppError, Conflict, NotFound

ACTIVE = (JobStatus.QUEUED, JobStatus.RUNNING)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------- plan
def build_plan(db: Session, p: ContentProject, job_type: VideoJobType, preview_seconds: int = 60) -> dict:
    settings = get_settings()
    ch = db.get(Channel, p.channel_id)
    lang = "vi" if (ch.language or "en").lower().startswith("vi") else "en"
    rs = p.render_settings or {}
    W, H = RESOLUTIONS.get(rs.get("resolution", "1920x1080"), (1920, 1080))
    fps = int(rs.get("fps", 30))
    if job_type == VideoJobType.PREVIEW:
        lo, hi = PREVIEW_SECONDS_RANGE
        duration = float(max(lo, min(hi, preview_seconds)))
    else:
        if p.duration_minutes not in DURATION_CHOICES:
            raise AppError(f"Thời lượng phải là một trong {DURATION_CHOICES} phút")
        duration = float(p.duration_minutes * 60)
    max_kbps = int(settings.render_max_bitrate_kbps * (W * H) / (1920 * 1080))

    bg = db.get(Asset, p.background_asset_id) if p.background_asset_id else None
    scene3d = None
    if p.scene3d:
        # 3D scene replaces the 2D background/character: same audio, timer overlay, queue and QC.
        sc = Scene3D(**p.scene3d)
        model_id = sc.character.asset_id
        model = db.get(Asset, model_id) if model_id else None
        if model_id and model is None:
            raise AppError("Model 3D của nhân vật không còn tồn tại")
        cap = max(1, int(round(fps / max(1, min(fps, settings.scene3d_fps)))))   # integer divisor of the video fps
        scene3d = {"scene": sc.model_dump(mode="json"), "model_path": model.file_path if model else None,
                   "capture_fps": max(1, fps // cap), "loop_seconds": float(min(settings.scene3d_loop_seconds, duration))}
    elif bg is None:
        raise AppError("Chưa chọn hình nền")
    anim = p.animation or {}
    character = None
    if p.character_id is not None and scene3d is None:
        v = pinned_version(db, p)
        img = character_image(v)
        if img:
            char = db.get(Character, p.character_id)
            placement = anim.get("character") or {}
            character = {
                "path": img, "character_id": p.character_id, "version_id": v.id, "version_no": v.version_no,
                "name": char.name if char else "", "position": placement.get("position", "bottom_right"),
                "scale": float(placement.get("scale", 0.42)), "motion": placement.get("motion", "bob"),
            }

    layers = []
    for i, l in enumerate(p.audio_layers or []):
        if l.get("kind") == "asset":
            a = db.get(Asset, l["asset_id"])
            if a is None:
                raise AppError(f"Tài nguyên âm thanh #{l['asset_id']} không còn tồn tại")
            layers.append({"kind": "asset", "asset_id": a.id, "path": a.file_path, "volume": l.get("volume", 0.8)})
        else:
            layers.append({"kind": "generator", "generator": l["generator"], "volume": l.get("volume", 0.8),
                           "seed": p.id * 100 + i + 1})

    overlay_cfg = dict(rs.get("overlay") or {})
    mode = overlay_cfg.get("mode", "none")
    phases = []
    if mode == "pomodoro" and p.pomodoro:
        pm = p.pomodoro
        phases = pomodoro_phases(duration, pm["focus_min"], pm["short_break_min"], pm["long_break_min"],
                                 pm["cycles_before_long"])
    elif mode == "countdown":
        phases = countdown_phases(duration)
    if scene3d is not None:
        # break_time reaction: the character reacts at the start of every break (placeholder always can; a .glb
        # needs a clip assigned to break_time)
        sc_char = scene3d["scene"]["character"]
        can_react = sc_char["asset_id"] is None or bool(sc_char["reactions"].get("break_time"))
        scene3d["break_starts"] = ([round(ph.start, 3) for ph in phases if ph.kind in ("short_break", "long_break")]
                                   if can_react else [])
    font_rel = None
    if overlay_cfg.get("font_asset_id"):
        fa = db.get(Asset, overlay_cfg["font_asset_id"])
        font_rel = fa.file_path if fa else None
    labels = {**DEFAULT_LABELS[lang], **(overlay_cfg.get("labels") or {})}
    palette = (ch.visual_style or {}).get("palette") or []

    return {
        "version": 1,
        "job_type": job_type.value,
        "channel_id": p.channel_id,
        "project_id": p.id,
        "title": p.youtube_title or p.title,
        "fingerprint": p.fingerprint,
        "duration_sec": duration,
        "width": W, "height": H, "fps": fps,
        "loop_seconds": int(min(settings.render_loop_seconds, duration)),
        "seed": p.id,
        "video": {"crf": int(rs.get("crf") or settings.render_crf),
                  "preset": rs.get("preset") or settings.render_preset, "max_bitrate_kbps": max_kbps},
        "audio": {"bitrate_kbps": settings.render_audio_bitrate_kbps, "chime_volume": rs.get("chime_volume", 0.6),
                  "master_volume": rs.get("master_volume", 1.0), "fade_in": 3.0,
                  "fade_out": 8.0 if duration >= 1800 else 3.0},
        "background": ({"asset_id": bg.id, "path": bg.file_path, "motion": anim.get("background_motion", "slow_zoom")}
                       if bg is not None else None),
        "scene3d": scene3d,
        "character": character,
        "effects": list(anim.get("effects") or []),
        "layers": layers,
        "overlay": {"mode": mode if phases else "none", "position": overlay_cfg.get("position", "top_center"),
                    "color": overlay_cfg.get("color", "#FFFFFF"), "box": overlay_cfg.get("box", True),
                    "labels": labels, "font_path": font_rel},
        "timeline": to_json(phases),
        "chime": bool(rs.get("chime")) and mode == "pomodoro" and bool(phases),
        "thumbnail": {"generate": not bool(p.thumbnail_path), "custom_path": p.thumbnail_path,
                      "title_text": p.youtube_title or p.title,
                      "badge": duration_label(int(duration // 60) or 1, lang).upper()
                      if job_type == VideoJobType.FULL else "PREVIEW",
                      "accent": palette[1] if len(palette) > 1 else (palette[0] if palette else "#E3A86B")},
    }


def job_timeout(duration: float) -> int:
    return int(max(3600, duration * get_settings().render_timeout_factor))


# ----------------------------------------------------------------- queue operations
def enqueue(db: Session, p: ContentProject, req: RenderRequest) -> VideoJob:
    try:
        job_type = VideoJobType(req.job_type)
    except ValueError as exc:
        raise AppError("job_type phải là 'full' hoặc 'preview'") from exc
    report = validate_for_render(db, p)
    if not report.ok:
        raise AppError("Chưa thể render: " + "; ".join(report.errors))
    active = db.scalar(select(VideoJob).where(VideoJob.content_project_id == p.id, VideoJob.status.in_(ACTIVE)))
    if active is not None:
        raise Conflict(f"Dự án đã có tác vụ #{active.id} đang chờ / đang chạy")
    plan = build_plan(db, p, job_type, req.preview_seconds)
    job = VideoJob(channel_id=p.channel_id, content_project_id=p.id, job_type=job_type, status=JobStatus.QUEUED,
                   priority=req.priority if job_type == VideoJobType.FULL else min(req.priority, 50),
                   render_config=plan, duration_sec=plan["duration_sec"], timeout_sec=job_timeout(plan["duration_sec"]),
                   max_attempts=2 if job_type == VideoJobType.FULL else 1, step="Đang chờ worker")
    db.add(job)
    if job_type == VideoJobType.FULL:
        p.status = ProductionStatus.QUEUED
        p.last_error = None
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("Dự án đã có tác vụ render đang chờ / đang chạy") from exc
    label = "bản xem thử" if job_type == VideoJobType.PREVIEW else "video"
    activity.record(db, "render", f"Đưa '{p.title}' vào hàng đợi render ({label}, "
                    f"{int(plan['duration_sec'])} s)", channel_id=p.channel_id, details={"job_id": job.id})
    db.commit()
    return job


def get_job(db: Session, job_id: int) -> VideoJob:
    j = db.get(VideoJob, job_id)
    if j is None:
        raise NotFound(f"Không tìm thấy tác vụ #{job_id}")
    return j


def cancel_job(db: Session, job: VideoJob) -> VideoJob:
    if job.status == JobStatus.QUEUED:
        job.status = JobStatus.CANCELLED
        job.finished_at = _now()
        job.step = "Đã hủy"
        p = db.get(ContentProject, job.content_project_id)
        if p is not None and job.job_type == VideoJobType.FULL and p.status == ProductionStatus.QUEUED:
            p.status = ProductionStatus.READY
    elif job.status == JobStatus.RUNNING:
        job.cancel_requested = True
        job.step = "Đang hủy…"
    else:
        raise Conflict(f"Tác vụ đang ở trạng thái '{job.status.value}', không thể hủy")
    activity.record(db, "render", f"Hủy tác vụ render #{job.id}", channel_id=job.channel_id)
    db.commit()
    return job


def retry_job(db: Session, job: VideoJob) -> VideoJob:
    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise Conflict("Chỉ chạy lại được tác vụ thất bại hoặc đã hủy")
    p = db.get(ContentProject, job.content_project_id)
    if p is None:
        raise NotFound("Dự án của tác vụ không còn tồn tại")
    lo, hi = PREVIEW_SECONDS_RANGE
    seconds = int(job.duration_sec or 60) if job.job_type == VideoJobType.PREVIEW else 60
    return enqueue(db, p, RenderRequest(job_type=job.job_type.value, preview_seconds=max(lo, min(hi, seconds)),
                                        priority=job.priority))


# ----------------------------------------------------------------- output
def job_out(db: Session, j: VideoJob, names: dict | None = None) -> JobOut:
    ch = db.get(Channel, j.channel_id)
    p = db.get(ContentProject, j.content_project_id)
    video_id = db.scalar(select(Video.id).where(Video.video_job_id == j.id)) if j.status == JobStatus.SUCCEEDED else None
    eta = None
    if j.status == JobStatus.RUNNING and j.started_at and j.progress > 0.02:
        elapsed = (_now() - j.started_at).total_seconds()
        eta = max(0.0, elapsed / j.progress - elapsed)
    log_ok = bool(j.log_path) and storage.file_size(j.log_path) > 0
    return JobOut(
        id=j.id, channel_id=j.channel_id, channel_name=ch.name if ch else "?", content_project_id=j.content_project_id,
        project_title=p.title if p else None, job_type=j.job_type.value, status=j.status.value, step=j.step,
        progress=round(j.progress, 4), attempts=j.attempts, max_attempts=j.max_attempts, priority=j.priority,
        worker_id=j.worker_id, heartbeat_at=j.heartbeat_at, started_at=j.started_at, finished_at=j.finished_at,
        created_at=j.created_at, duration_sec=j.duration_sec, timeout_sec=j.timeout_sec,
        cancel_requested=j.cancel_requested, error=j.error,
        output_url=storage.media_url(j.output_path) if j.status == JobStatus.SUCCEEDED else None,
        video_id=video_id, eta_seconds=eta, has_log=log_ok,
    )


def list_jobs(db: Session, *, channel_id: int | None = None, project_id: int | None = None,
              status: JobStatus | None = None, limit: int = 100) -> list[JobOut]:
    stmt = select(VideoJob)
    if channel_id is not None:
        stmt = stmt.where(VideoJob.channel_id == channel_id)
    if project_id is not None:
        stmt = stmt.where(VideoJob.content_project_id == project_id)
    if status is not None:
        stmt = stmt.where(VideoJob.status == status)
    rows = db.scalars(stmt.order_by(VideoJob.created_at.desc(), VideoJob.id.desc()).limit(min(max(limit, 1), 500)))
    return [job_out(db, j) for j in rows]


def job_log(job: VideoJob, max_bytes: int = 64_000) -> str:
    if not job.log_path:
        return ""
    try:
        path = storage.resolve(job.log_path)
    except storage.StorageError:
        return ""
    if not path.exists():
        return ""
    with path.open("rb") as fh:
        size = path.stat().st_size
        fh.seek(max(0, size - max_bytes))
        return fh.read().decode("utf-8", errors="replace")


def video_out(db: Session, v: Video) -> VideoOut:
    ch = db.get(Channel, v.channel_id)
    return VideoOut(
        id=v.id, channel_id=v.channel_id, channel_name=ch.name if ch else "?", content_project_id=v.content_project_id,
        video_job_id=v.video_job_id, title=v.title, url=storage.media_url(v.file_path) or "",
        thumbnail_url=storage.media_url(v.thumbnail_path), duration_sec=v.duration_sec, width=v.width,
        height=v.height, fps=v.fps, size_bytes=v.size_bytes, sha256=v.sha256,
        qc_passed=bool((v.qc_report or {}).get("passed")), qc_report=v.qc_report,
        youtube_video_id=v.youtube_video_id, privacy_status=v.privacy_status.value if v.privacy_status else None,
        created_at=v.created_at,
    )


def list_videos(db: Session, channel_id: int | None = None, project_id: int | None = None) -> list[VideoOut]:
    stmt = select(Video)
    if channel_id is not None:
        stmt = stmt.where(Video.channel_id == channel_id)
    if project_id is not None:
        stmt = stmt.where(Video.content_project_id == project_id)
    return [video_out(db, v) for v in db.scalars(stmt.order_by(Video.created_at.desc(), Video.id.desc()))]


def get_video(db: Session, video_id: int) -> Video:
    v = db.get(Video, video_id)
    if v is None:
        raise NotFound(f"Không tìm thấy video #{video_id}")
    return v


def delete_video(db: Session, v: Video) -> None:
    if v.youtube_video_id:
        raise Conflict("Video đã được đăng lên YouTube; không xóa file gốc tại đây")
    files = [v.file_path, v.thumbnail_path]
    title, cid, pid = v.title, v.channel_id, v.content_project_id
    db.delete(v)
    if pid is not None:
        remaining = db.scalar(select(func.count()).select_from(Video).where(
            Video.channel_id == cid, Video.content_project_id == pid, Video.id != v.id)) or 0
        p = db.get(ContentProject, pid)
        if p is not None and not remaining and p.status == ProductionStatus.RENDERED:
            p.status = ProductionStatus.READY
    activity.record(db, "render", f"Xóa video '{title}'", channel_id=cid)
    db.commit()
    for f in files:
        storage.delete_file(f)
    if files[0]:
        try:
            d = storage.resolve(files[0]).parent
            if d.exists() and not any(d.iterdir()):
                d.rmdir()
        except (storage.StorageError, OSError):
            pass


# ----------------------------------------------------------------- worker / capabilities
def worker_out(w: WorkerStatus) -> WorkerOut:
    limit = timedelta(seconds=get_settings().worker_heartbeat_seconds * 3 + 10)
    online = w.state != "stopped" and (_now() - w.heartbeat_at) < limit
    return WorkerOut(worker_id=w.worker_id, kind=w.kind, hostname=w.hostname, pid=w.pid,
                     state=w.state.value if hasattr(w.state, "value") else str(w.state), online=online,
                     current_job_id=w.current_job_id, started_at=w.started_at,
                     heartbeat_at=w.heartbeat_at, info=w.info)


def production_status(db: Session) -> ProductionStatusOut:
    workers = [worker_out(w) for w in db.scalars(
        select(WorkerStatus).where(WorkerStatus.kind == "render").order_by(WorkerStatus.heartbeat_at.desc())).all()]
    since = _now() - timedelta(hours=24)

    def count(*conds) -> int:  # noqa: ANN002
        return int(db.scalar(select(func.count()).select_from(VideoJob).where(*conds)) or 0)

    return ProductionStatusOut(
        workers=workers, queued=count(VideoJob.status == JobStatus.QUEUED),
        running=count(VideoJob.status == JobStatus.RUNNING),
        failed_24h=count(VideoJob.status == JobStatus.FAILED, VideoJob.finished_at >= since),
        succeeded_24h=count(VideoJob.status == JobStatus.SUCCEEDED, VideoJob.finished_at >= since),
    )


def capabilities() -> Capabilities:
    settings = get_settings()
    path = version = None
    drawtext = False
    try:
        path = ff.ffmpeg_bin()
        version = ff.ffmpeg_version(path)[2]
        drawtext = ff.has_filter("drawtext", path)
    except Exception:  # noqa: BLE001 - reported as missing
        pass
    font = find_font()
    return Capabilities(
        scene3d=scene3d_render.status(),
        ffmpeg_path=path, ffmpeg_version=version, ffprobe_path=ff.ffprobe_bin() if path else None,
        drawtext=drawtext, font_path=str(font) if font else None, render_threads=ff.render_threads(),
        render_preset=settings.render_preset, render_crf=settings.render_crf,
        loop_seconds=settings.render_loop_seconds, durations=list(DURATION_CHOICES),
        preview_seconds=list(PREVIEW_SECONDS_RANGE),
        generators={k: {"label": v["label"], "description": v["description"]} for k, v in GENERATORS.items()},
        background_motions=BACKGROUND_MOTIONS, effects=EFFECTS, character_motions=CHARACTER_MOTIONS,
        character_positions=list(CHARACTER_POSITIONS), overlay_modes=OVERLAY_MODES,
        overlay_positions=list(OVERLAY_POSITIONS), background_styles=BACKGROUND_STYLES,
        resolutions=list(RESOLUTIONS), x264_presets=list(X264_PRESETS),
    )


def output_dir_for(job: VideoJob) -> Path:
    if job.job_type == VideoJobType.PREVIEW:
        return Path("channels") / str(job.channel_id) / "previews" / str(job.id)
    return Path("channels") / str(job.channel_id) / "videos" / str(job.content_project_id) / str(job.id)


def cleanup_old_previews(db: Session, project_id: int, keep: int = 3) -> None:
    """Keep only the latest `keep` preview renders of a project on disk."""
    old = db.scalars(select(VideoJob).where(VideoJob.content_project_id == project_id,
                                            VideoJob.job_type == VideoJobType.PREVIEW,
                                            VideoJob.status == JobStatus.SUCCEEDED,
                                            VideoJob.output_path.is_not(None))
                     .order_by(VideoJob.created_at.desc()).offset(keep)).all()
    for j in old:
        try:
            d = storage.resolve(j.output_path).parent
            shutil.rmtree(d, ignore_errors=True)
        except storage.StorageError:
            pass
        j.output_path = None
