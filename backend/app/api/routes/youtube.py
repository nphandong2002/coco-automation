"""YouTube connection (OAuth) per channel."""
from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.integrations.youtube import oauth
from app.schemas.publishing import AuthUrlOut, PlaylistOut, YoutubeConfigOut, YoutubeStatusOut
from app.services import channel_service, youtube_service
from app.services.errors import AppError

log = logging.getLogger("coco.youtube")
router = APIRouter(tags=["youtube"])


@router.get("/youtube/config", response_model=YoutubeConfigOut)
def config():
    return youtube_service.config_info()


@router.get("/youtube/oauth/callback", include_in_schema=False)
def oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None,
                   db: Session = Depends(get_db)):
    """Google redirects the browser here. We finish the flow and send the user back to the dashboard."""
    channel_id = None
    if state:
        try:
            channel_id = oauth.read_state(state)
        except oauth.OAuthError:
            pass
    back = f"/channels/{channel_id}" if channel_id else "/channels"
    if error or not code or not state:
        msg = "Bạn đã từ chối cấp quyền" if error == "access_denied" else f"Google báo lỗi: {error or 'thiếu mã'}"
        return RedirectResponse(f"{back}?youtube=error&message={quote(msg)}", status_code=303)
    try:
        ch = youtube_service.complete_connect(db, code, state)
    except AppError as exc:
        return RedirectResponse(f"{back}?youtube=error&message={quote(exc.message)}", status_code=303)
    return RedirectResponse(f"/channels/{ch.id}?youtube=connected", status_code=303)


@router.get("/channels/{channel_id}/youtube", response_model=YoutubeStatusOut)
def youtube_status(channel_id: int, db: Session = Depends(get_db)):
    return youtube_service.status(channel_service.get_channel(db, channel_id))


@router.post("/channels/{channel_id}/youtube/connect", response_model=AuthUrlOut)
def connect(channel_id: int, db: Session = Depends(get_db)):
    ch = channel_service.get_channel(db, channel_id)
    return {"auth_url": youtube_service.begin_connect(ch)}


@router.post("/channels/{channel_id}/youtube/disconnect", response_model=YoutubeStatusOut)
def disconnect(channel_id: int, db: Session = Depends(get_db)):
    ch = youtube_service.disconnect(db, channel_service.get_channel(db, channel_id))
    return youtube_service.status(ch)


@router.get("/channels/{channel_id}/youtube/playlists", response_model=list[PlaylistOut])
def playlists(channel_id: int, db: Session = Depends(get_db)):
    ch = channel_service.get_channel(db, channel_id)
    if not ch.youtube_connected:
        raise AppError("Kênh chưa kết nối YouTube", 409)
    return youtube_service.list_playlists(ch.id)
