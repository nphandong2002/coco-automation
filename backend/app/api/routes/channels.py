from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.channel import ChannelClone, ChannelCreate, ChannelOut, ChannelSummary, ChannelUpdate
from app.schemas.system import LogOut
from app.services import channel_service as svc
from app.services.overview_service import recent_logs

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=list[ChannelOut])
def list_channels(db: Session = Depends(get_db)):
    return svc.list_channels(db)


@router.post("", response_model=ChannelOut, status_code=201)
def create_channel(data: ChannelCreate, db: Session = Depends(get_db)):
    return svc.channel_out(db, svc.create_channel(db, data))


@router.get("/{channel_id}", response_model=ChannelOut)
def get_channel(channel_id: int, db: Session = Depends(get_db)):
    return svc.channel_out(db, svc.get_channel(db, channel_id))


@router.patch("/{channel_id}", response_model=ChannelOut)
def update_channel(channel_id: int, data: ChannelUpdate, db: Session = Depends(get_db)):
    ch = svc.get_channel(db, channel_id)
    return svc.channel_out(db, svc.update_channel(db, ch, data))


@router.delete("/{channel_id}", status_code=204)
def delete_channel(channel_id: int, confirm: str = Query(..., description="Nhập mã kênh để xác nhận"),
                   db: Session = Depends(get_db)):
    svc.delete_channel(db, svc.get_channel(db, channel_id), confirm)


@router.post("/{channel_id}/enable", response_model=ChannelOut)
def enable_channel(channel_id: int, db: Session = Depends(get_db)):
    return svc.channel_out(db, svc.set_enabled(db, svc.get_channel(db, channel_id), True))


@router.post("/{channel_id}/pause", response_model=ChannelOut)
def pause_channel(channel_id: int, db: Session = Depends(get_db)):
    return svc.channel_out(db, svc.set_enabled(db, svc.get_channel(db, channel_id), False))


@router.post("/{channel_id}/clear-error", response_model=ChannelOut)
def clear_error(channel_id: int, db: Session = Depends(get_db)):
    return svc.channel_out(db, svc.clear_error(db, svc.get_channel(db, channel_id)))


@router.post("/{channel_id}/clone", response_model=ChannelOut, status_code=201)
def clone_channel(channel_id: int, data: ChannelClone, db: Session = Depends(get_db)):
    return svc.channel_out(db, svc.clone_channel(db, svc.get_channel(db, channel_id), data))


@router.post("/{channel_id}/avatar", response_model=ChannelOut)
def upload_avatar(channel_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = file.file.read()
    return svc.channel_out(db, svc.save_brand_image(db, svc.get_channel(db, channel_id), "avatar", data))


@router.post("/{channel_id}/banner", response_model=ChannelOut)
def upload_banner(channel_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = file.file.read()
    return svc.channel_out(db, svc.save_brand_image(db, svc.get_channel(db, channel_id), "banner", data))


@router.get("/{channel_id}/summary", response_model=ChannelSummary)
def channel_summary(channel_id: int, db: Session = Depends(get_db)):
    return svc.channel_summary(db, svc.get_channel(db, channel_id))


@router.get("/{channel_id}/activity", response_model=list[LogOut])
def channel_activity(channel_id: int, limit: int = 30, db: Session = Depends(get_db)):
    svc.get_channel(db, channel_id)
    return recent_logs(db, limit, channel_id=channel_id)
