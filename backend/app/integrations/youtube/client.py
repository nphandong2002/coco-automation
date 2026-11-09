"""Thin YouTube Data API v3 client (httpx): channel info, playlists, resumable upload, thumbnails.

Design notes
  * Resumable upload: the session URI is persisted by the caller after `start_upload`, so after a
    crash/restart `upload_file` asks YouTube how many bytes it already has and continues.
  * Every failure is classified (`ApiError.kind`) so the publisher can decide: retry, wait for
    quota reset, reconnect the channel, or fail permanently.
  * No attempt is made to bypass quota limits, CAPTCHA or 2FA.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

import httpx

from app.core.config import get_settings

log = logging.getLogger("coco.youtube")

API = "https://www.googleapis.com/youtube/v3"
UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3"
CHUNK_ALIGN = 256 * 1024

# ApiError.kind
RETRYABLE = "retryable"        # 5xx, network, rate limit: try again with backoff
QUOTA = "quota"                # daily quota exhausted: retry after quota reset
AUTH = "auth"                  # token rejected / revoked: channel must reconnect
PERMANENT = "permanent"        # bad request, forbidden, not found: retrying cannot help


class ApiError(RuntimeError):
    def __init__(self, message: str, kind: str, status: int | None = None, reason: str = "") -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.reason = reason


def classify(status: int, reason: str) -> str:
    reason = (reason or "").lower()
    if reason in ("quotaexceeded", "dailylimitexceeded", "ratelimitexceeded", "userratelimitexceeded"):
        return QUOTA if reason in ("quotaexceeded", "dailylimitexceeded") else RETRYABLE
    if reason in ("uploadlimitexceeded",):
        return QUOTA
    if status == 401 or reason in ("autherror", "invalidcredentials"):
        return AUTH
    if status in (408, 429) or status >= 500:
        return RETRYABLE
    return PERMANENT


def _error_from_response(r: httpx.Response) -> ApiError:
    reason, message = "", ""
    try:
        err = r.json().get("error", {})
        message = err.get("message", "")
        errors = err.get("errors") or []
        reason = (errors[0].get("reason") if errors else "") or err.get("status", "")
    except (ValueError, AttributeError):
        message = r.text[:200]
    kind = classify(r.status_code, reason)
    return ApiError(f"YouTube API {r.status_code} {reason}: {message}".strip(), kind, r.status_code, reason)


class YouTubeClient:
    """`token_getter(force_refresh)` returns a valid access token (refreshing when asked)."""

    def __init__(self, token_getter: Callable[[bool], str], http: httpx.Client | None = None) -> None:
        self._token_getter = token_getter
        self._owns = http is None
        self.http = http or httpx.Client(timeout=get_settings().youtube_http_timeout_sec)

    def close(self) -> None:
        if self._owns:
            self.http.close()

    def __enter__(self) -> "YouTubeClient":
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        self.close()

    # ---------------------------------------------------------------- plumbing
    def _request(self, method: str, url: str, *, ok: tuple[int, ...] = (200,), **kw) -> httpx.Response:
        """Send with bearer token; on 401 refresh the token once and retry."""
        force = False
        for attempt in range(2):
            headers = {**kw.pop("headers", {}), "Authorization": f"Bearer {self._token_getter(force)}"}
            try:
                r = self.http.request(method, url, headers=headers, **kw)
            except httpx.HTTPError as exc:
                raise ApiError(f"Lỗi mạng khi gọi YouTube: {exc.__class__.__name__}: {exc}", RETRYABLE) from exc
            if r.status_code == 401 and attempt == 0:
                force = True
                kw["headers"] = {k: v for k, v in headers.items() if k != "Authorization"}
                continue
            if r.status_code in ok:
                return r
            raise _error_from_response(r)
        raise ApiError("YouTube từ chối token", AUTH, 401)  # pragma: no cover

    # ---------------------------------------------------------------- read
    def my_channel(self) -> dict:
        r = self._request("GET", f"{API}/channels", params={"part": "snippet,statistics", "mine": "true"})
        items = r.json().get("items") or []
        if not items:
            raise ApiError("Tài khoản Google này chưa có kênh YouTube", PERMANENT, 200, "noChannel")
        return items[0]

    def my_playlists(self) -> list[dict]:
        out: list[dict] = []
        token = None
        while True:
            params = {"part": "snippet,status", "mine": "true", "maxResults": 50}
            if token:
                params["pageToken"] = token
            data = self._request("GET", f"{API}/playlists", params=params).json()
            out += data.get("items", [])
            token = data.get("nextPageToken")
            if not token:
                return out

    def get_json(self, url: str, params: dict) -> dict:
        """Authenticated GET returning JSON (token refresh + error classification included)."""
        return self._request("GET", url, params=params).json()

    def videos_statistics(self, video_ids: list[str]) -> dict[str, dict]:
        """Data API `videos.list` (statistics + status), batched by 50. Missing/private-deleted ids are absent."""
        out: dict[str, dict] = {}
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            data = self.get_json(f"{API}/videos", {"part": "statistics,status", "id": ",".join(batch), "maxResults": 50})
            for item in data.get("items", []):
                out[item["id"]] = item
        return out

    def video_status(self, video_id: str) -> dict | None:
        r = self._request("GET", f"{API}/videos", params={"part": "status,processingDetails", "id": video_id})
        items = r.json().get("items") or []
        return items[0] if items else None

    # ---------------------------------------------------------------- upload
    @staticmethod
    def build_metadata(*, title: str, description: str, tags: list[str], category_id: str,
                       privacy: str, publish_at_iso: str | None) -> dict:
        status: dict = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
        if publish_at_iso:
            # YouTube requires private + publishAt for scheduled publication
            status["privacyStatus"] = "private"
            status["publishAt"] = publish_at_iso
        return {
            "snippet": {"title": title, "description": description, "tags": tags, "categoryId": category_id},
            "status": status,
        }

    def start_upload(self, metadata: dict, size: int, mime: str = "video/mp4") -> str:
        r = self._request(
            "POST", f"{UPLOAD_API}/videos",
            params={"uploadType": "resumable", "part": "snippet,status"},
            json=metadata,
            headers={"X-Upload-Content-Length": str(size), "X-Upload-Content-Type": mime},
        )
        uri = r.headers.get("location")
        if not uri:
            raise ApiError("YouTube không trả session upload", RETRYABLE, r.status_code)
        return uri

    def _query_offset(self, uri: str, size: int) -> tuple[int, dict | None]:
        """Ask YouTube how much of the file it already has. Returns (offset, video_json_if_complete)."""
        r = self.http.put(uri, headers={"Content-Range": f"bytes */{size}", "Content-Length": "0"})
        if r.status_code in (200, 201):
            return size, r.json()
        if r.status_code == 308:
            rng = r.headers.get("range")  # "bytes=0-12345"
            return (int(rng.split("-")[1]) + 1 if rng else 0), None
        if r.status_code == 404:
            raise ApiError("Session upload đã hết hạn", RETRYABLE, 404, "sessionExpired")
        raise _error_from_response(r)

    def upload_file(self, uri: str, path: Path, *, resume: bool = False,
                    on_progress: Callable[[int, int], None] | None = None,
                    should_stop: Callable[[], bool] | None = None) -> dict:
        """Upload `path` through a resumable session; returns the created video resource.

        Raises ApiError(kind=RETRYABLE, reason='sessionExpired') when the session URI is dead and
        the caller must start a new session.
        """
        size = path.stat().st_size
        chunk = max(CHUNK_ALIGN, (get_settings().youtube_upload_chunk_mb * 1024 * 1024 // CHUNK_ALIGN) * CHUNK_ALIGN)
        offset = 0
        if resume:  # existing session: ask YouTube what it already has
            try:
                offset, done = self._query_offset(uri, size)
            except httpx.HTTPError as exc:
                raise ApiError(f"Lỗi mạng khi tiếp tục upload: {exc}", RETRYABLE) from exc
            if done is not None:
                return done
        with path.open("rb") as f:
            while offset < size:
                if should_stop and should_stop():
                    raise ApiError("Upload bị dừng (worker tắt)", RETRYABLE, reason="stopped")
                end = min(offset + chunk, size) - 1
                data = _read_range(f, offset, end - offset + 1)
                headers = {"Content-Range": f"bytes {offset}-{end}/{size}", "Content-Type": "video/mp4"}
                try:
                    r = self.http.put(uri, content=data, headers=headers,
                                      timeout=max(120.0, get_settings().youtube_http_timeout_sec * 2))
                except httpx.HTTPError as exc:
                    raise ApiError(f"Lỗi mạng khi upload: {exc.__class__.__name__}", RETRYABLE) from exc
                if r.status_code in (200, 201):
                    if on_progress:
                        on_progress(size, size)
                    return r.json()
                if r.status_code == 308:
                    rng = r.headers.get("range")
                    offset = int(rng.split("-")[1]) + 1 if rng else offset
                    if on_progress:
                        on_progress(offset, size)
                    continue
                if r.status_code == 404:
                    raise ApiError("Session upload đã hết hạn", RETRYABLE, 404, "sessionExpired")
                if r.status_code == 401:
                    raise ApiError("Token bị từ chối khi upload", RETRYABLE, 401, "tokenExpired")
                raise _error_from_response(r)
        raise ApiError("Upload kết thúc nhưng YouTube không trả video", RETRYABLE)

    # ---------------------------------------------------------------- after upload
    def set_thumbnail(self, video_id: str, data: bytes, mime: str) -> None:
        self._request("POST", f"{UPLOAD_API}/thumbnails/set", params={"videoId": video_id},
                      content=data, headers={"Content-Type": mime})

    def add_to_playlist(self, playlist_id: str, video_id: str) -> None:
        body = {"snippet": {"playlistId": playlist_id,
                            "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
        self._request("POST", f"{API}/playlistItems", params={"part": "snippet"}, json=body)


def _read_range(f: BinaryIO, offset: int, length: int) -> bytes:
    f.seek(offset)
    return f.read(length)


def backoff_seconds(attempt: int) -> int:
    s = get_settings()
    return int(min(s.publish_retry_max_sec, s.publish_retry_base_sec * (2 ** max(0, attempt - 1))))


def now_ts() -> float:
    return time.time()
