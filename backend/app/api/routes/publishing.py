"""Publishing Manager: upload queue, scheduling, history."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import WorkerStatus
from app.models.enums import JobStatus
from app.schemas.publishing import PublishCreate, PublishJobOut, PublishStatusOut, SlotsOut
from app.services import channel_service, publish_service as svc

router = APIRouter(tags=["publishing"])


@router.get("/publishing/status", response_model=PublishStatusOut)
def status(db: Session = Depends(get_db)):
    from app.services.render_service import worker_out  # reuse the same worker serialisation
    workers = [worker_out(w) for w in db.scalars(select(WorkerStatus).where(WorkerStatus.kind == "publish"))]
    return {"counts": svc.queue_status(db), "workers": [w.model_dump(mode="json") for w in workers]}


@router.get("/publishing/jobs", response_model=list[PublishJobOut])
def list_jobs(channel_id: int | None = None, status: JobStatus | None = None, limit: int = 100,
              db: Session = Depends(get_db)):
    return svc.list_jobs(db, channel_id, status, limit)


@router.get("/publishing/jobs/{job_id}", response_model=PublishJobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    return svc.job_out(db, svc.get_job(db, job_id))


@router.post("/channels/{channel_id}/publishing/jobs", response_model=PublishJobOut, status_code=201)
def create_job(channel_id: int, data: PublishCreate, db: Session = Depends(get_db)):
    ch = channel_service.get_channel(db, channel_id)
    return svc.job_out(db, svc.create_job(db, ch, data))


@router.post("/publishing/jobs/{job_id}/cancel", response_model=PublishJobOut)
def cancel(job_id: int, db: Session = Depends(get_db)):
    return svc.job_out(db, svc.cancel_job(db, svc.get_job(db, job_id)))


@router.post("/publishing/jobs/{job_id}/retry", response_model=PublishJobOut)
def retry(job_id: int, db: Session = Depends(get_db)):
    return svc.job_out(db, svc.retry_job(db, svc.get_job(db, job_id)))


@router.get("/channels/{channel_id}/publishing/slots", response_model=SlotsOut)
def slots(channel_id: int, count: int = Query(5, ge=1, le=30), db: Session = Depends(get_db)):
    ch = channel_service.get_channel(db, channel_id)
    return {"timezone": (ch.publish_schedule or {}).get("timezone") or "UTC",
            "slots": svc.next_slots(db, ch, count)}
