"""Logging configuration: console + rotating file."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.core.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    if any(getattr(h, "_coco", False) for h in root.handlers):
        return

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console._coco = True  # type: ignore[attr-defined]
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        settings.log_dir / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler._coco = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)
