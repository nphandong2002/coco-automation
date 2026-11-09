"""Font discovery for timer overlays (FFmpeg drawtext) and thumbnails (Pillow)."""
from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings

# Bold first: timers/thumbnails read better in bold. DejaVu covers Vietnamese diacritics.
CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
)


def find_font(preferred: str | Path | None = None) -> Path | None:
    for c in (preferred, get_settings().font_path or None, *CANDIDATES):
        if c and Path(c).is_file():
            return Path(c)
    return None


def quote_option(value: str) -> str:
    """Make `value` safe as ONE filter option value inside a filtergraph.

    Two escaping levels (see ffmpeg-filters "Notes on filtergraph escaping"):
      1. option level: backslash and ':' are escaped with a backslash
      2. graph level: the whole value is wrapped in single quotes (taken literally)
    Single quotes cannot appear inside, so they are replaced by a typographic apostrophe.
    """
    v = value.replace("'", "\u2019").replace("\\", "\\\\").replace(":", "\\:")
    return f"'{v}'"


def escape_filter_path(path: Path | str) -> str:
    """Quoted, escaped path for drawtext fontfile= (works for Windows 'C:/...' paths too)."""
    return quote_option(str(path).replace("\\", "/"))
