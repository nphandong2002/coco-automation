"""Per-channel YouTube connection: OAuth connect/disconnect, token refresh, playlists."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.integrations.youtube import oauth
from app.integrations.youtube.client import ApiError, YouTubeClient
from app.models import Channel, YoutubeCredential
from app.models.enums import CredentialStatus, LogLevel
from app.services import activity
from app.services.errors import AppError, Conflict

REFRESH_MARGIN_SEC = 120


def _now() -> datetime:
    return datetime.now(timezone.utc)


def config_info() -> dict:
    from app.core.config import get_settings
    s = get_settings()
    return {"configured": oauth.is_configured(), "redirect_uri": s.oauth_redirect_uri, "scopes": oauth.SCOPES}


def status(ch: Channel) -> dict:
    c = ch.credential
    return {
        "configured": oauth.is_configured(),
        "connected": ch.youtube_connected,
        "status": c.status.value if c else "disconnected",
        "youtube_channel_id": c.youtube_channel_id if c else None,
        "youtube_channel_title": c.youtube_channel_title if c else None,
        "google_account_email": c.google_account_email if c else None,
        "scopes": c.scopes if c else [],
        "token_expiry": c.token_expiry if c else None,
        "last_refresh_at": c.last_refresh_at if c else None,
        "last_error": c.last_error if c else None,
    }


# ---------------------------------------------------------------- connect
def begin_connect(ch: Channel) -> str:
    try:
        return oauth.build_auth_url(ch.id)
    except oauth.OAuthNotConfigured as exc:
        raise AppError(str(exc), 503) from exc


def complete_connect(db: Session, code: str, state: str, http: httpx.Client | None = None) -> Channel:
    """OAuth callback. Stores the encrypted token for the channel encoded in `state`."""
    try:
        channel_id = oauth.read_state(state)
    except oauth.OAuthError as exc:
        raise AppError(str(exc), 400) from exc
    ch = db.get(Channel, channel_id)
    if ch is None:
        raise AppError("Kênh không còn tồn tại", 404)
    try:
        token = oauth.exchange_code(code, http)
    except oauth.OAuthError as exc:
        raise AppError(str(exc), 400) from exc

    client = YouTubeClient(lambda _force: token["access_token"], http)
    try:
        info = client.my_channel()
    except ApiError as exc:
        raise AppError(f"Không đọc được kênh YouTube: {exc}", 400) from exc
    finally:
        client.close()
    yt_id = info["id"]
    title = info.get("snippet", {}).get("title")

    other = db.scalar(select(YoutubeCredential).where(YoutubeCredential.youtube_channel_id == yt_id,
                                                      YoutubeCredential.channel_id != ch.id))
    if other is not None:
        raise Conflict(f"Kênh YouTube '{title}' đã được kết nối với một kênh Coco khác (#{other.channel_id}). "
                       "Mỗi kênh YouTube chỉ gắn với một kênh Coco.")

    cred = db.scalar(select(YoutubeCredential).where(YoutubeCredential.channel_id == ch.id))
    scopes = [s for s in token["scope"].split() if s]
    expiry = datetime.fromtimestamp(token["expires_at"], tz=timezone.utc)
    if cred is None:
        cred = YoutubeCredential(channel_id=ch.id, token_encrypted=token)
        db.add(cred)
    cred.token_encrypted = token
    cred.token_expiry = expiry
    cred.youtube_channel_id = yt_id
    cred.youtube_channel_title = title
    cred.scopes = scopes
    cred.status = CredentialStatus.VALID
    cred.last_error = None
    cred.last_refresh_at = _now()
    if ch.last_error and ch.last_error.startswith("YouTube"):
        ch.last_error = None
        ch.last_error_at = None
    activity.record(db, "youtube", f"Đã kết nối YouTube '{title}'", channel_id=ch.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("Kênh YouTube này đã được kết nối ở nơi khác") from exc
    db.refresh(ch)
    return ch


def disconnect(db: Session, ch: Channel, http: httpx.Client | None = None) -> Channel:
    cred = ch.credential
    if cred is None:
        raise AppError("Kênh chưa kết nối YouTube", 400)
    try:
        token = cred.token_encrypted.get("refresh_token") or cred.token_encrypted.get("access_token")
    except Exception:  # noqa: BLE001 - undecryptable token must not block disconnecting
        token = None
    if token:
        oauth.revoke(token, http)
    title = cred.youtube_channel_title
    db.delete(cred)
    activity.record(db, "youtube", f"Đã ngắt kết nối YouTube '{title}'", channel_id=ch.id)
    db.commit()
    db.refresh(ch)
    return ch


# ---------------------------------------------------------------- tokens
def mark_revoked(channel_id: int, reason: str) -> None:
    """Refresh token no longer valid: this channel must reconnect. Other channels are untouched."""
    with SessionLocal() as db:
        cred = db.scalar(select(YoutubeCredential).where(YoutubeCredential.channel_id == channel_id))
        ch = db.get(Channel, channel_id)
        if cred is not None:
            cred.status = CredentialStatus.REVOKED
            cred.last_error = reason[:1000]
        if ch is not None:
            ch.last_error = "YouTube: cần kết nối lại — " + reason[:200]
            ch.last_error_at = _now()
        activity.record(db, "youtube", f"Token YouTube bị thu hồi: {reason[:200]}", channel_id=channel_id,
                        level=LogLevel.ERROR)
        db.commit()


def token_getter(channel_id: int, http: httpx.Client | None = None):
    """Returns f(force_refresh) -> access_token, refreshing + persisting when needed."""

    def get(force: bool = False) -> str:
        with SessionLocal() as db:
            cred = db.scalar(select(YoutubeCredential).where(YoutubeCredential.channel_id == channel_id))
            if cred is None or cred.status != CredentialStatus.VALID:
                raise ApiError("Kênh chưa kết nối YouTube hoặc cần kết nối lại", "auth", 401)
            tok = dict(cred.token_encrypted)
            if not force and tok.get("expires_at", 0) - time.time() > REFRESH_MARGIN_SEC:
                return tok["access_token"]
            try:
                new = oauth.refresh(tok["refresh_token"], http)
            except oauth.OAuthError as exc:
                if exc.revoked:
                    mark_revoked(channel_id, str(exc))
                    raise ApiError(str(exc), "auth", 401) from exc
                raise ApiError(str(exc), "retryable") from exc
            cred.token_encrypted = {**tok, **new}
            cred.token_expiry = datetime.fromtimestamp(new["expires_at"], tz=timezone.utc)
            cred.last_refresh_at = _now()
            cred.last_error = None
            db.commit()
            return new["access_token"]

    return get


def client_for(channel_id: int, http: httpx.Client | None = None) -> YouTubeClient:
    return YouTubeClient(token_getter(channel_id, http), http)


def list_playlists(channel_id: int, http: httpx.Client | None = None) -> list[dict]:
    client = client_for(channel_id, http)
    try:
        items = client.my_playlists()
    except ApiError as exc:
        raise AppError(f"Không đọc được playlist: {exc}", 502 if exc.kind != "auth" else 401) from exc
    finally:
        client.close()
    return [{"id": p["id"], "title": p.get("snippet", {}).get("title", ""),
             "privacy": p.get("status", {}).get("privacyStatus")} for p in items]
