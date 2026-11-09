"""Google OAuth 2.0 (authorization-code flow) for YouTube — one authorisation per channel.

The `state` parameter is a short-lived Fernet token carrying the Coco channel id, so the
callback cannot be replayed for another channel and no server-side state is needed.
No CAPTCHA / 2FA handling: the user signs in on Google's own consent screen.
"""
from __future__ import annotations

import json
import secrets
import time
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.security import decrypt_bytes, encrypt_bytes

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",  # Phase 4
]
STATE_TTL_SEC = 600


class OAuthError(RuntimeError):
    def __init__(self, message: str, *, revoked: bool = False) -> None:
        super().__init__(message)
        self.revoked = revoked  # refresh token no longer valid -> user must reconnect


class OAuthNotConfigured(OAuthError):
    pass


def require_config() -> tuple[str, str]:
    s = get_settings()
    if not s.google_client_id or not s.google_client_secret:
        raise OAuthNotConfigured(
            "Chưa cấu hình Google OAuth: đặt GOOGLE_CLIENT_ID và GOOGLE_CLIENT_SECRET trong .env "
            "(xem docs/YOUTUBE_SETUP.md)")
    return s.google_client_id, s.google_client_secret


def is_configured() -> bool:
    s = get_settings()
    return bool(s.google_client_id and s.google_client_secret)


def make_state(channel_id: int) -> str:
    payload = {"c": channel_id, "t": int(time.time()), "n": secrets.token_hex(8)}
    return encrypt_bytes(json.dumps(payload).encode()).decode()


def read_state(state: str) -> int:
    try:
        payload = json.loads(decrypt_bytes(state.encode()))
        if time.time() - int(payload["t"]) > STATE_TTL_SEC:
            raise OAuthError("Phiên kết nối đã hết hạn, hãy bấm 'Kết nối YouTube' lại")
        return int(payload["c"])
    except OAuthError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise OAuthError("State OAuth không hợp lệ") from exc


def build_auth_url(channel_id: int) -> str:
    client_id, _ = require_config()
    params = {
        "client_id": client_id,
        "redirect_uri": get_settings().oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",      # refresh token
        "prompt": "consent select_account",  # always return a refresh token + let user pick the channel's account
        "include_granted_scopes": "true",
        "state": make_state(channel_id),
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _post_token(data: dict, http: httpx.Client | None = None) -> dict:
    s = get_settings()
    owns = http is None
    http = http or httpx.Client(timeout=s.youtube_http_timeout_sec)
    try:
        r = http.post(TOKEN_URL, data=data)
    except httpx.HTTPError as exc:
        raise OAuthError(f"Không kết nối được Google: {exc}") from exc
    finally:
        if owns:
            http.close()
    body = {}
    try:
        body = r.json()
    except ValueError:
        pass
    if r.status_code != 200:
        err = body.get("error", "")
        msg = body.get("error_description") or err or f"HTTP {r.status_code}"
        raise OAuthError(f"Google từ chối: {msg}", revoked=err == "invalid_grant")
    return body


def exchange_code(code: str, http: httpx.Client | None = None) -> dict:
    client_id, secret = require_config()
    body = _post_token({
        "code": code, "client_id": client_id, "client_secret": secret,
        "redirect_uri": get_settings().oauth_redirect_uri, "grant_type": "authorization_code",
    }, http)
    if not body.get("refresh_token"):
        raise OAuthError("Google không trả refresh token. Hãy gỡ quyền của ứng dụng tại "
                         "myaccount.google.com/permissions rồi kết nối lại")
    return _normalise(body)


def refresh(refresh_token: str, http: httpx.Client | None = None) -> dict:
    client_id, secret = require_config()
    body = _post_token({
        "refresh_token": refresh_token, "client_id": client_id, "client_secret": secret,
        "grant_type": "refresh_token",
    }, http)
    out = _normalise(body)
    out.setdefault("refresh_token", refresh_token)
    return out


def _normalise(body: dict) -> dict:
    return {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token"),
        "expires_at": time.time() + int(body.get("expires_in", 3600)),
        "scope": body.get("scope", ""),
    }


def revoke(token: str, http: httpx.Client | None = None) -> None:
    """Best effort: failure to revoke must not block disconnecting locally."""
    owns = http is None
    http = http or httpx.Client(timeout=15)
    try:
        http.post(REVOKE_URL, data={"token": token})
    except httpx.HTTPError:
        pass
    finally:
        if owns:
            http.close()
