from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import check_database, get_db
from app.schemas.system import LogOut, Overview, SystemInfo
from app.services import overview_service as svc

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    ok, msg = check_database()
    return {"status": "ok" if ok else "degraded", "database": msg, "version": get_settings().app_version}


@router.get("/overview", response_model=Overview)
def overview(db: Session = Depends(get_db)):
    return svc.overview(db)


@router.get("/system/info", response_model=SystemInfo)
def system_info(db: Session = Depends(get_db)):
    return svc.system_info(db)


@router.get("/system/logs", response_model=list[LogOut])
def system_logs(limit: int = 100, channel_id: int | None = None, category: str | None = None,
                db: Session = Depends(get_db)):
    return svc.recent_logs(db, limit, channel_id=channel_id, category=category)
