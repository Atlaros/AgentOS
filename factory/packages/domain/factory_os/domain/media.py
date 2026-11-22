"""Unified media storage for catalog (and later chat/attachments). ADR-015."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from factory_os.domain.catalog_images import (
    MAX_IMAGE_BYTES,
    _safe_segment,
    _thumbnail,
    _write,
    sniff_image,
)

THUMB_CACHE_MAX_AGE_S = 7 * 24 * 3600
ORIGINAL_CACHE_MAX_AGE_S = 3600


def media_root() -> Path:
    """Bytes root: MEDIA_DIR, else CATALOG_IMAGES_DIR, else data/media."""
    for key in ("MEDIA_DIR", "CATALOG_IMAGES_DIR"):
        env = (os.environ.get(key) or "").strip()
        if env:
            return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "db" / "migrations").is_dir():
            return parent / "data" / "media"
    return Path.cwd() / "data" / "media"


@dataclass(frozen=True)
class StoredImageKeys:
    storage_key: str
    thumb_key: str
    mime: str
    size_bytes: int


def store_catalog_media_image(
    tenant_id: UUID, product_sku: str, data: bytes
) -> StoredImageKeys:
    """Write original + ~300px thumb under media_root. Returns relative keys."""
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
    root = media_root()
    _write(root, image_key, data)
    try:
        thumb = _thumbnail(data)
    except Exception as exc:
        raise ValueError("bad_type") from exc
    _write(root, thumb_key, thumb)
    return StoredImageKeys(
        storage_key=image_key,
        thumb_key=thumb_key,
        mime=kind,
        size_bytes=len(data),
    )


def read_media_bytes(storage_key: str, *, root: Path | None = None) -> bytes:
    """Read bytes for a storage key under the media root."""
    base = root if root is not None else media_root()
    path = base.joinpath(*Path(storage_key).parts)
    if not path.is_file():
        raise FileNotFoundError(storage_key)
    return path.read_bytes()


def _media_cache_variant(variant: str) -> str:
    """Normalize a serve variant to ``thumb`` or ``original``."""
    token = (variant or "").strip().lower()
    if token == "thumb":
        return "thumb"
    if token in {"original", "full"}:
        return "original"
    raise ValueError("bad_variant")


def media_cache_headers(*, variant: str, asset_id: UUID, size_bytes: int) -> dict[str, str]:
    """Private browser cache headers for an authenticated media response."""
    token = _media_cache_variant(variant)
    max_age = THUMB_CACHE_MAX_AGE_S if token == "thumb" else ORIGINAL_CACHE_MAX_AGE_S
    return {
        "Cache-Control": f"private, max-age={max_age}",
        "ETag": f'"{asset_id.hex}-{token}-{size_bytes}"',
    }


def _etag_validator(value: str) -> str:
    token = value.strip()
    if token[:2].upper() == "W/":
        token = token[2:].strip()
    if len(token) >= 2 and token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    return token


def media_etag_matches(if_none_match: str | None, etag: str) -> bool:
    """True when ``If-None-Match`` names ``etag`` (quotes and weak ``W/`` ignored)."""
    if if_none_match is None or not if_none_match.strip():
        return False
    wanted = _etag_validator(etag)
    return any(_etag_validator(part) == wanted for part in if_none_match.split(","))


def media_thumb_url(asset_id: UUID) -> str:
    return f"/api/media/{asset_id}?variant=thumb"


def primary_media_fields(
    store: object, tenant_id: UUID, product_sku: str, *, attrs: dict | None = None
) -> tuple[str, str]:
    """Return ``(media_id, thumb_url)`` for a product's primary media.

    Prefers ``product_media`` primary link; falls back to ``attrs["media_id"]``.
    """
    media_id = ""
    thumb_url = ""
    list_media = getattr(store, "list_product_media", None)
    if callable(list_media) and product_sku:
        try:
            links = list_media(tenant_id, product_sku)
        except Exception:
            links = []
        primary = next((row for row in links if row.is_primary), links[0] if links else None)
        if primary is not None:
            media_id = str(primary.asset_id)
            thumb_url = media_thumb_url(primary.asset_id)
            return media_id, thumb_url
    raw = ""
    if attrs:
        raw = str(attrs.get("media_id") or "").strip()
    if raw:
        try:
            media_id = str(UUID(raw))
            thumb_url = media_thumb_url(UUID(raw))
        except (ValueError, TypeError):
            media_id = ""
            thumb_url = ""
    return media_id, thumb_url


def primary_product_media_link(store: object, tenant_id: UUID, product_sku: str):
    """Return the primary ``ProductMedia`` link, or the first gallery row, or None."""
    list_media = getattr(store, "list_product_media", None)
    if not callable(list_media) or not product_sku:
        return None
    try:
        links = list_media(tenant_id, product_sku)
    except Exception:
        return None
    if not links:
        return None
    return next((row for row in links if getattr(row, "is_primary", False)), links[0])


def product_image_caption(store: object, tenant_id: UUID, product_sku: str) -> str:
    """Build WhatsApp caption from Postgres/memory catalog facts (never from the model)."""
    from factory_os.domain.stock import tracks_stock

    variants = [
        record
        for record in store.iter_variants()
        if getattr(record, "product_sku", None) == product_sku
    ]
    if not variants:
        return ""
    head = variants[0]
    name = str(head.name or product_sku).strip()
    price = str(head.price)
    currency = str(head.currency or "BOB")
    in_stock: list[str] = []
    for record in variants:
        size = str((record.attributes or {}).get("size") or "").strip()
        label = size or str(record.variant_sku)
        if not tracks_stock(record):
            in_stock.append(label)
        elif int(record.stock or 0) >= 1 and not (record.attributes or {}).get("disabled"):
            in_stock.append(f"{label} ({record.stock})")
    lines = [f"{name} · {price} {currency}"]
    if in_stock:
        lines.append("Disponible: " + ", ".join(in_stock))
    return "\n".join(lines)
