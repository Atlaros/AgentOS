"""Conversation media links and inbound/outbound store helpers (ADR-015 Fase C)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from uuid import UUID, uuid4

from factory_os.domain.catalog_images import _safe_segment, _thumbnail, _write, sniff_image
from factory_os.domain.media import media_root, media_thumb_url
from factory_os.domain.models import ConversationMedia, MediaAsset

logger = logging.getLogger(__name__)

MediaDownloader = Callable[..., tuple[bytes, str]]

MAX_BYTES_BY_KIND = {
    "image": 5 * 1024 * 1024,
    "audio": 16 * 1024 * 1024,
    "video": 16 * 1024 * 1024,
    "document": 16 * 1024 * 1024,
}

ALLOWED_MIME = {
    "image": {"image/jpeg", "image/png", "image/webp"},
    "audio": {"audio/mpeg", "audio/ogg", "audio/mp4", "audio/aac", "audio/ogg; codecs=opus"},
    "video": {"video/mp4", "video/3gpp"},
    "document": {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/plain",
    },
}

_RECEIPT_DEFAULT = "te envío el comprobante de pago"
_UNSAFE_NAME = re.compile(r"[^\w.\-]+", re.UNICODE)


@dataclass(frozen=True)
class StoredChatKeys:
    storage_key: str
    thumb_key: str | None
    mime: str
    size_bytes: int
    kind: str


class ChatMediaError(ValueError):
    """Invalid chat media (type/size)."""


def sanitize_filename(name: str | None, *, fallback: str = "file") -> str:
    cleaned = _UNSAFE_NAME.sub("_", (name or "").strip()).strip("._") or fallback
    return cleaned[:120]


def sniff_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def resolve_mime(kind: str, declared: str | None, data: bytes) -> str:
    declared_norm = (declared or "").split(";", 1)[0].strip().lower()
    if kind == "image":
        sniffed = sniff_image(data)
        if sniffed is None:
            raise ChatMediaError("bad_type")
        return sniffed
    if kind == "document":
        if sniff_pdf(data):
            return "application/pdf"
        if declared_norm in ALLOWED_MIME["document"]:
            return declared_norm
        raise ChatMediaError("bad_type")
    if kind in {"audio", "video"}:
        if declared_norm and declared_norm.split(";", 1)[0] in {
            m.split(";", 1)[0] for m in ALLOWED_MIME[kind]
        }:
            return declared_norm
        # Accept declared family match (audio/*, video/*) when sniff is unavailable.
        family = kind + "/"
        if declared_norm.startswith(family):
            return declared_norm
        raise ChatMediaError("bad_type")
    raise ChatMediaError("bad_type")


def validate_chat_bytes(kind: str, data: bytes, declared_mime: str | None = None) -> str:
    if not data:
        raise ChatMediaError("empty_file")
    limit = MAX_BYTES_BY_KIND.get(kind, MAX_BYTES_BY_KIND["document"])
    if len(data) > limit:
        raise ChatMediaError("file_too_large")
    mime = resolve_mime(kind, declared_mime, data)
    allowed = ALLOWED_MIME.get(kind) or set()
    bare = mime.split(";", 1)[0].strip().lower()
    if kind == "audio" and bare.startswith("audio/"):
        return mime
    if kind == "video" and bare.startswith("video/"):
        return mime
    if bare not in {m.split(";", 1)[0] for m in allowed} and mime not in allowed:
        raise ChatMediaError("bad_type")
    return mime


def receipt_origin(kind: str, text_for_origin: str, caption: str | None) -> str:
    """Pick media_assets.origin: receipt vs chat_inbound. Never confirms payment."""
    if kind not in {"image", "document"}:
        return "chat_inbound"
    body = (text_for_origin or "").strip().lower()
    cap = (caption or "").strip().lower()
    if not cap and body == _RECEIPT_DEFAULT:
        return "receipt"
    if "comprobante" in body or "comprobante" in cap or "voucher" in body:
        return "receipt"
    return "chat_inbound"


def store_chat_bytes(
    tenant_id: UUID,
    *,
    kind: str,
    data: bytes,
    mime: str,
    filename: str | None = None,
    folder: str = "chat",
) -> StoredChatKeys:
    """Write chat bytes under media_root; thumb only for images."""
    mime = validate_chat_bytes(kind, data, mime)
    stamp = uuid4().hex
    safe_name = sanitize_filename(filename, fallback=kind)
    ext = Path(safe_name).suffix.lstrip(".")
    if not ext:
        ext = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/webp": "webp",
            "application/pdf": "pdf",
        }.get(mime.split(";", 1)[0], "bin")
    base = f"{tenant_id}/{_safe_segment(folder)}/{stamp}"
    storage_key = f"{base}.{ext}"
    root = media_root()
    _write(root, storage_key, data)
    thumb_key: str | None = None
    if kind == "image":
        try:
            thumb_key = f"{base}_thumb.jpg"
            _write(root, thumb_key, _thumbnail(data))
        except Exception:
            thumb_key = None
    return StoredChatKeys(
        storage_key=storage_key,
        thumb_key=thumb_key,
        mime=mime.split(";", 1)[0],
        size_bytes=len(data),
        kind=kind,
    )


def _link_payload(
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    asset_id: UUID | None,
    provider_ref: str | None,
    message_index: int | None,
    direction: str,
    status: str,
    kind: str,
    mime: str | None,
    filename: str | None,
    size_bytes: int | None,
    error: str | None,
    uploaded_by: str | None,
) -> ConversationMedia:
    return ConversationMedia(
        id=uuid4(),
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        asset_id=asset_id,
        provider_ref=(provider_ref or "").strip() or None,
        message_index=message_index,
        direction=direction,
        status=status,
        kind=kind,
        mime=mime,
        filename=filename,
        size_bytes=size_bytes,
        error=error,
        uploaded_by=uploaded_by,
        created_at=datetime.now(UTC),
    )


def store_inbound_chat_media(
    store,
    tenant_id: UUID,
    *,
    conversation_id: UUID,
    provider_ref: str | None,
    media_id: str | None,
    media_kind: str,
    mime: str | None,
    filename: str | None,
    caption: str | None,
    text_for_origin: str,
    message_index: int | None,
    downloader: MediaDownloader | None = None,
    access_token: str = "",
) -> ConversationMedia:
    """Download + validate + store inbound media; dedup by provider_ref (wamid)."""
    store.require_tenant(tenant_id)
    ref = (provider_ref or "").strip() or None
    if ref:
        existing = store.get_conversation_media_by_provider_ref(tenant_id, ref)
        if existing is not None:
            return existing

    kind = (media_kind or "document").strip().lower()
    if kind not in MAX_BYTES_BY_KIND:
        kind = "document"

    mid = (media_id or "").strip()
    if not mid or downloader is None:
        link = _link_payload(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            asset_id=None,
            provider_ref=ref,
            message_index=message_index,
            direction="inbound",
            status="failed",
            kind=kind,
            mime=mime,
            filename=filename,
            size_bytes=None,
            error="missing_downloader" if downloader is None else "missing_media_id",
            uploaded_by=None,
        )
        return store.add_conversation_media(tenant_id, link)

    try:
        data, declared = downloader(mid, access_token=access_token)
        resolved = validate_chat_bytes(kind, data, mime or declared)
        keys = store_chat_bytes(
            tenant_id,
            kind=kind,
            data=data,
            mime=resolved,
            filename=filename,
            folder="chat",
        )
        origin = receipt_origin(kind, text_for_origin, caption)
        asset = MediaAsset(
            id=uuid4(),
            tenant_id=tenant_id,
            kind=keys.kind,
            mime=keys.mime,
            size_bytes=keys.size_bytes,
            storage_key=keys.storage_key,
            origin=origin,
            thumb_key=keys.thumb_key,
            uploaded_by=None,
            provider_ref=ref,
            created_at=datetime.now(UTC),
        )
        # Dedup asset by provider_ref if already present.
        if ref:
            prior = store.get_media_asset_by_provider_ref(tenant_id, ref)
            if prior is not None:
                asset = prior
            else:
                asset = store.add_media_asset(tenant_id, asset)
        else:
            asset = store.add_media_asset(tenant_id, asset)
        link = _link_payload(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            asset_id=asset.id,
            provider_ref=ref,
            message_index=message_index,
            direction="inbound",
            status="ready",
            kind=asset.kind,
            mime=asset.mime,
            filename=sanitize_filename(filename, fallback=kind) if filename else None,
            size_bytes=asset.size_bytes,
            error=None,
            uploaded_by=None,
        )
        return store.add_conversation_media(tenant_id, link)
    except Exception as exc:
        logger.warning(
            "inbound chat media failed conversation=%s ref=%s",
            conversation_id,
            (ref or "")[:32],
            exc_info=False,
        )
        code = str(exc) if isinstance(exc, ChatMediaError) else "download_failed"
        if isinstance(exc, ChatMediaError):
            code = str(exc)
        link = _link_payload(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            asset_id=None,
            provider_ref=ref,
            message_index=message_index,
            direction="inbound",
            status="failed",
            kind=kind,
            mime=mime,
            filename=filename,
            size_bytes=None,
            error=code[:120],
            uploaded_by=None,
        )
        return store.add_conversation_media(tenant_id, link)


def store_outbound_chat_media(
    store,
    tenant_id: UUID,
    *,
    conversation_id: UUID,
    kind: str,
    data: bytes,
    mime: str | None,
    filename: str | None,
    message_index: int | None,
    uploaded_by: str | None,
) -> tuple[ConversationMedia, MediaAsset]:
    """Validate + store staff outbound media (origin chat_outbound)."""
    store.require_tenant(tenant_id)
    resolved_kind = (kind or "document").strip().lower()
    if resolved_kind not in {"image", "document"}:
        raise ChatMediaError("bad_type")
    keys = store_chat_bytes(
        tenant_id,
        kind=resolved_kind,
        data=data,
        mime=mime or "",
        filename=filename,
        folder="chat_out",
    )
    asset = MediaAsset(
        id=uuid4(),
        tenant_id=tenant_id,
        kind=keys.kind,
        mime=keys.mime,
        size_bytes=keys.size_bytes,
        storage_key=keys.storage_key,
        origin="chat_outbound",
        thumb_key=keys.thumb_key,
        uploaded_by=uploaded_by,
        provider_ref=None,
        created_at=datetime.now(UTC),
    )
    asset = store.add_media_asset(tenant_id, asset)
    link = _link_payload(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        asset_id=asset.id,
        provider_ref=None,
        message_index=message_index,
        direction="outbound",
        status="ready",
        kind=asset.kind,
        mime=asset.mime,
        filename=sanitize_filename(filename, fallback=resolved_kind),
        size_bytes=asset.size_bytes,
        error=None,
        uploaded_by=uploaded_by,
    )
    return store.add_conversation_media(tenant_id, link), asset


def media_view(link: ConversationMedia, asset: MediaAsset | None = None) -> dict[str, object]:
    """API shape for a conversation media row."""
    thumb = None
    asset_id = str(link.asset_id) if link.asset_id else None
    origin = asset.origin if asset is not None else None
    if link.status == "ready" and link.asset_id and (link.kind == "image" or (asset and asset.thumb_key)):
        thumb = media_thumb_url(link.asset_id)
    return {
        "id": str(link.id),
        "asset_id": asset_id,
        "kind": link.kind,
        "mime": link.mime,
        "filename": link.filename,
        "size_bytes": link.size_bytes,
        "thumb_url": thumb,
        "status": link.status,
        "direction": link.direction,
        "origin": origin,
        "error": link.error,
        "uploaded_by": link.uploaded_by,
        "provider_ref": link.provider_ref,
        "message_index": link.message_index,
        "created_at": link.created_at.isoformat() if link.created_at else None,
        "transcript_text": link.transcript_text,
        "summary_text": link.summary_text,
        "enrichment_status": link.enrichment_status or "none",
        "enrichment_error": link.enrichment_error,
    }
