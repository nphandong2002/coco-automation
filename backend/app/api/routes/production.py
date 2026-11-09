"""Video Production: render queue, worker status, rendered videos."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.enums import JobStatus
from app.schemas.production import Capabilities, JobOut, ProductionStatusOut, VideoOut
from app.services import render_service as svc

router = APIRouter(prefix="/production", tags=["production"])


@router.get("/capabilities", response_model=Capabilities)
def capabilities():
    return svc.capabilities()


@router.get("/status", response_model=ProductionStatusOut)
def status(db: Session = Depends(get_db)):
    return svc.production_status(db)


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(channel_id: int | None = None, status: JobStatus | None = None, limit: int = 100,
              db: Session = Depends(get_db)):
    return svc.list_jobs(db, channel_id=channel_id, status=status, limit=limit)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    return svc.job_out(db, svc.get_job(db, job_id))


@router.get("/jobs/{job_id}/log", response_class=PlainTextResponse)
def job_log(job_id: int, db: Session = Depends(get_db)):
    return svc.job_log(svc.get_job(db, job_id)) or "(chưa có log)"


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    return svc.job_out(db, svc.cancel_job(db, svc.get_job(db, job_id)))


@router.post("/jobs/{job_id}/retry", response_model=JobOut, status_code=201)
def retry_job(job_id: int, db: Session = Depends(get_db)):
    return svc.job_out(db, svc.retry_job(db, svc.get_job(db, job_id)))


@router.get("/videos", response_model=list[VideoOut])
def list_videos(channel_id: int | None = None, project_id: int | None = None, db: Session = Depends(get_db)):
    return svc.list_videos(db, channel_id, project_id)


@router.get("/videos/{video_id}", response_model=VideoOut)
def get_video(video_id: int, db: Session = Depends(get_db)):
    return svc.video_out(db, svc.get_video(db, video_id))


@router.delete("/videos/{video_id}", status_code=204)
def delete_video(video_id: int, db: Session = Depends(get_db)):
    svc.delete_video(db, svc.get_video(db, video_id))
