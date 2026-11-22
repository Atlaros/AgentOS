"""Catalog photos live on disk. Postgres stores the path, not the bytes."""

from __future__ import annotations

import io
import os
import re
from pathlib import Path
from uuid import UUID, uuid4

MAX_IMAGE_BYTES = 2 * 1024 * 1024
THUMB_EDGE = 300
_UNSAFE = re.compile(r"[^\w.\-]+", re.UNICODE)


def catalog_images_root() -> Path:
    """Directory for catalog image bytes. MEDIA_DIR, else CATALOG_IMAGES_DIR."""
    for key in ("MEDIA_DIR", "CATALOG_IMAGES_DIR"):
        env = (os.environ.get(key) or "").strip()
        if env:
            return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "db" / "migrations").is_dir():
            return parent / "data" / "catalog_images"
    return Path.cwd() / "data" / "catalog_images"


def sniff_image(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _safe_segment(value: str) -> str:
    cleaned = _UNSAFE.sub("_", (value or "").strip()).strip("._") or "product"
    return cleaned[:80]


def _write(root: Path, key: str, data: bytes) -> None:
    path = root.joinpath(*Path(key).parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _thumbnail(data: bytes) -> bytes:
    from PIL import Image

    image = Image.open(io.BytesIO(data))
    image.thumbnail((THUMB_EDGE, THUMB_EDGE))
    if image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


def store_catalog_image(tenant_id: UUID, product_sku: str, data: bytes) -> tuple[str, str]:
    """Write the original and a ~300px thumbnail. Returns relative keys."""
    if not data:
        raise ValueError("empty_file")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("file_too_large")
    kind = sniff_image(data)
    if kind is None:
        raise ValueError("bad_type")
    extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[kind]
    folder = f"{tenant_id}/{_safe_segment(product_sku)}"
    stamp = uuid4().hex
    image_key = f"{folder}/{stamp}.{extension}"
    thumb_key = f"{folder}/{stamp}_thumb.jpg"
    root = catalog_images_root()
    _write(root, image_key, data)
    try:
        thumb = _thumbnail(data)
    except Exception as exc:
        raise ValueError("bad_type") from exc
    _write(root, thumb_key, thumb)
    return image_key, thumb_key
