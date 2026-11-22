"""Supplier directory helpers (ADR-012 T1). Soft-deactivate only; no hard delete."""

from __future__ import annotations

from typing import Any, Iterable
from uuid import UUID

from factory_os.domain.models import Supplier
from factory_os.domain.store import VariantRecord


def list_low_stock(store: Any, *, limit: int | None = None) -> list[VariantRecord]:
    """Variants at or below their per-variant reorder threshold."""
    rows = [
        record
        for record in store.iter_variants()
        if not record.attributes.get("disabled")
        and record.stock <= int(getattr(record, "reorder_threshold", 1) or 1)
    ]
    if limit is not None:
        return rows[: max(0, int(limit))]
    return rows


def supplier_public(supplier: Supplier) -> dict[str, Any]:
    return {
        "id": str(supplier.id),
        "name": supplier.name,
        "contact_name": supplier.contact_name,
        "phone": supplier.phone,
        "whatsapp": supplier.whatsapp,
        "email": supplier.email,
        "notes": supplier.notes,
        "payment_terms": supplier.payment_terms,
        "lead_time_days": supplier.lead_time_days,
        "active": supplier.active,
        "created_at": supplier.created_at.isoformat() if supplier.created_at else None,
        "updated_at": supplier.updated_at.isoformat() if supplier.updated_at else None,
    }


def low_stock_public(records: Iterable[VariantRecord], *, limit: int = 50) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for record in records:
        if len(out) >= limit:
            break
        out.append(
            {
                "variant_sku": record.variant_sku,
                "name": record.name,
                "codigo": str(record.attributes.get("codigo") or ""),
                "stock": record.stock,
                "reorder_threshold": int(getattr(record, "reorder_threshold", 1) or 1),
                "supplier_id": str(record.supplier_id) if record.supplier_id else None,
            }
        )
    return out
