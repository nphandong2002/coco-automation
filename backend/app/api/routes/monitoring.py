"""System monitoring API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import monitor_service, recovery

router = APIRouter(tags=["monitoring"])


@router.get("/monitoring")
def snapshot(db: Session = Depends(get_db)):
    return monitor_service.snapshot(db)


@router.get("/monitoring/history")
def history(hours: int = Query(6, ge=1, le=168), db: Session = Depends(get_db)):
    return monitor_service.history(db, hours)


@router.post("/monitoring/maintenance")
def run_maintenance(db: Session = Depends(get_db)):
    """Run housekeeping now (prune old logs/metrics/temp files, kill orphan FFmpeg)."""
    return recovery.maintenance(db)


@router.post("/monitoring/watchdog")
def run_watchdog(db: Session = Depends(get_db)):
    """Run the hung-job check now; returns the actions taken (empty list = nothing was stuck)."""
    return {"actions": recovery.watchdog(db)}
