"""YouTube Analytics API v2 (`reports.query`) — read-only.

Only documented queries are used; metrics are returned exactly as YouTube reports them and no
value is invented. A missing day simply is not returned (the caller must not fill it with zeros).
"""
from __future__ import annotations

from datetime import date

from app.integrations.youtube.client import PERMANENT, ApiError, YouTubeClient

REPORTS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"

CHANNEL_DAILY_METRICS = [
    "views", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage",
    "subscribersGained", "subscribersLost", "likes", "comments",
]
VIDEO_DAILY_METRICS = [
    "views", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage",
    "subscribersGained", "likes", "comments",
]


def query(client: YouTubeClient, *, start: date, end: date, metrics: list[str], dimensions: str | None = None,
          filters: str | None = None, sort: str | None = None, max_results: int | None = None) -> list[dict]:
    """Run one report; returns rows as {column_name: value}. Empty list = YouTube has no data."""
    params: dict = {"ids": "channel==MINE", "startDate": start.isoformat(), "endDate": end.isoformat(),
                    "metrics": ",".join(metrics)}
    if dimensions:
        params["dimensions"] = dimensions
    if filters:
        params["filters"] = filters
    if sort:
        params["sort"] = sort
    if max_results:
        params["maxResults"] = max_results
    data = client.get_json(REPORTS_URL, params)
    names = [h["name"] for h in data.get("columnHeaders", [])]
    return [dict(zip(names, row)) for row in data.get("rows") or []]


def channel_daily(client: YouTubeClient, start: date, end: date) -> list[dict]:
    return query(client, start=start, end=end, metrics=CHANNEL_DAILY_METRICS, dimensions="day", sort="day")


def video_daily(client: YouTubeClient, youtube_video_id: str, start: date, end: date) -> list[dict]:
    return query(client, start=start, end=end, metrics=VIDEO_DAILY_METRICS, dimensions="day",
                 filters=f"video=={youtube_video_id}", sort="day")


def video_retention(client: YouTubeClient, youtube_video_id: str, start: date, end: date) -> list[list[float]]:
    """[[elapsedVideoTimeRatio, audienceWatchRatio], ...] sorted by elapsed ratio."""
    rows = query(client, start=start, end=end, metrics=["audienceWatchRatio"],
                 dimensions="elapsedVideoTimeRatio", filters=f"video=={youtube_video_id}",
                 sort="elapsedVideoTimeRatio")
    return [[float(r["elapsedVideoTimeRatio"]), float(r["audienceWatchRatio"])] for r in rows
            if r.get("audienceWatchRatio") is not None]


def is_scope_error(exc: ApiError) -> bool:
    """403 from the Analytics API = the token lacks the yt-analytics scope or the API is not enabled."""
    return exc.kind == PERMANENT and exc.status == 403
