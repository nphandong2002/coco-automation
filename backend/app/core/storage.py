"""File storage on local disk.

Layout (every file is scoped by channel to keep channels isolated):

    storage/
      channels/<channel_id>/brand/<sha256>.<ext>
      channels/<channel_id>/characters/<character_id>/<sha256>.<ext>
      shared/...                      (Phase 2: shared asset library)

Files are content-addressed (sha256) so identical uploads are stored once and
immutable character versions can reference them safely.
"""
from __future__ import annotations

import hashlib
import io
import shutil
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings

ALLOWED_IMAGE_FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}


class StorageError(ValueError):
    pass


def storage_root() -> Path:
    root = get_settings().storage_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def channel_dir(channel_id: int) -> Path:
    return storage_root() / "channels" / str(int(channel_id))


def save_image(data: bytes, rel_dir: Path, max_side: int = 4096) -> dict:
    """Validate and persist an image. Returns {path, sha256, width, height, size}."""
    settings = get_settings()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise StorageError(f"File quá lớn (tối đa {settings.max_upload_mb} MB)")
    if not data:
        raise StorageError("File rỗng")
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format
            width, height = img.size
    except (UnidentifiedImageError, OSError) as exc:
        raise StorageError("File không phải ảnh hợp lệ (PNG/JPEG/WEBP)") from exc
    if fmt not in ALLOWED_IMAGE_FORMATS:
        raise StorageError(f"Định dạng {fmt} không được hỗ trợ. Dùng PNG, JPEG hoặc WEBP")
    if width > max_side * 2 or height > max_side * 2:
        raise StorageError("Kích thước ảnh quá lớn")

    digest = hashlib.sha256(data).hexdigest()
    ext = ALLOWED_IMAGE_FORMATS[fmt]
    rel_path = rel_dir / f"{digest}.{ext}"
    abs_path = storage_root() / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    if not abs_path.exists():
        tmp = abs_path.with_suffix(abs_path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(abs_path)  # atomic on same filesystem
    return {
        "path": rel_path.as_posix(),
        "sha256": digest,
        "width": width,
        "height": height,
        "size": len(data),
    }


def copy_file(rel_src: str, rel_dst_dir: Path) -> str:
    """Copy a stored file into another directory (used when cloning channels)."""
    src = resolve(rel_src)
    dst = storage_root() / rel_dst_dir / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(src, dst)
    return (rel_dst_dir / src.name).as_posix()


def resolve(rel_path: str) -> Path:
    root = storage_root().resolve()
    p = (root / rel_path).resolve()
    if root not in p.parents and p != root:
        raise StorageError("Đường dẫn không hợp lệ")
    return p


def remove_channel_files(channel_id: int) -> None:
    d = channel_dir(channel_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def media_url(rel_path: str | None) -> str | None:
    return f"/media/{rel_path}" if rel_path else None
