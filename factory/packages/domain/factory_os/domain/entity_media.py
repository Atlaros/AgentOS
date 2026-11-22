"""Order / purchase-order attachments via media_assets (ADR-015 Fase E)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from factory_os.domain.catalog_images import sniff_image
from factory_os.domain.chat_media import (
    ChatMediaError,
    sanitize_filename,
    sniff_pdf,
    store_chat_bytes,
)
from factory_os.domain.media import media_thumb_url
from factory_os.domain.models import EntityMedia, MediaAsset

ENTITY_ORDER = "order"
ENTITY_PURCHASE_ORDER = "purchase_order"

_ORIGIN = {
    ENTITY_ORDER: "order_attachment",
    ENTITY_PURCHASE_ORDER: "purchase_attachment",
}
_FOLDER = {
    ENTITY_ORDER: "orders",
    ENTITY_PURCHASE_ORDER: "purchases",
}


class EntityMediaError(ValueError):
    """Invalid entity attachment (type/size/entity)."""


def _resolve_kind_and_mime(data: bytes, declared_mime: str | None) -> tuple[str, str]:
    if not data:
        raise EntityMediaError("empty_file")
    sniffed = sniff_image(data)
    if sniffed is not None:
        return "image", sniffed
    if sniff_pdf(data):
        return "document", "application/pdf"
    declared = (declared_mime or "").split(";", 1)[0].strip().lower()
    if declared.startswith("image/") or declared == "application/pdf":
        # Declared image/pdf but bytes do not match → reject.
        raise EntityMediaError("bad_type")
    raise EntityMediaError("bad_type")


def store_entity_attachment(
    store,
    tenant_id: UUID,
    *,
    entity_type: str,
    entity_id: UUID,
    data: bytes,
    mime: str | None,
    filename: str | None,
    uploaded_by: str | None,
    note: str | None = None,
) -> EntityMedia:
    """Validate image/pdf, write under media_root, link EntityMedia. No payment/stock side effects."""
    store.require_tenant(tenant_id)
    etype = (entity_type or "").strip().lower()
    if etype not in _ORIGIN:
        raise EntityMediaError("unknown_entity")
    if etype == ENTITY_ORDER:
        if store.get_order(tenant_id, entity_id) is None:
            raise EntityMediaError("unknown_entity")
    else:
        if store.get_purchase_order(tenant_id, entity_id) is None:
            raise EntityMediaError("unknown_entity")

    try:
        kind, resolved_mime = _resolve_kind_and_mime(data, mime)
        keys = store_chat_bytes(
            tenant_id,
            kind=kind,
            data=data,
            mime=resolved_mime,
            filename=filename,
            folder=_FOLDER[etype],
        )
    except ChatMediaError as exc:
        raise EntityMediaError(str(exc) or "bad_type") from exc

    safe_name = sanitize_filename(filename, fallback=kind)
    asset = MediaAsset(
        id=uuid4(),
        tenant_id=tenant_id,
        kind=keys.kind,
        mime=keys.mime,
        size_bytes=keys.size_bytes,
        storage_key=keys.storage_key,
        origin=_ORIGIN[etype],
        thumb_key=keys.thumb_key,
        uploaded_by=uploaded_by,
        provider_ref=None,
        created_at=datetime.now(UTC),
    )
    asset = store.add_media_asset(tenant_id, asset)
    link = EntityMedia(
        id=uuid4(),
        tenant_id=tenant_id,
        entity_type=etype,
        entity_id=entity_id,
        asset_id=asset.id,
        filename=safe_name,
        kind=asset.kind,
        mime=asset.mime,
        size_bytes=asset.size_bytes,
        note=(note or "").strip() or None,
        uploaded_by=uploaded_by,
        created_at=datetime.now(UTC),
    )
    return store.add_entity_media(tenant_id, link)


def entity_media_view(link: EntityMedia, asset: MediaAsset | None = None) -> dict[str, object]:
    """Staff-facing attachment row for the panel API."""
    _ = asset  # reserved for future enrichment; bytes served via GET /api/media
    thumb: str | None = media_thumb_url(link.asset_id) if link.kind == "image" else None
    return {
        "id": str(link.id),
        "asset_id": str(link.asset_id),
        "filename": link.filename,
        "kind": link.kind,
        "mime": link.mime,
        "size_bytes": link.size_bytes,
        "thumb_url": thumb,
        "url": f"/api/media/{link.asset_id}",
        "note": link.note,
        "uploaded_by": link.uploaded_by,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }
