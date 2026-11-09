"""Activity / audit log written to `system_logs`."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import SystemLog
from app.models.enums import LogLevel

log = logging.getLogger("coco.activity")


def record(
    db: Session,
    category: str,
    message: str,
    *,
    channel_id: int | None = None,
    level: LogLevel = LogLevel.INFO,
    details: dict | None = None,
) -> None:
    """Add a log row to the current transaction (committed with the business change)."""
    db.add(
        SystemLog(
            category=category,
            message=message[:500],
            channel_id=channel_id,
            level=level,
            details=details or {},
        )
    )
    log.log(logging.getLevelName(level.value.upper()), "[%s] ch=%s %s", category, channel_id, message)
