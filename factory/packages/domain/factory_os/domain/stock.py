"""Sell a quantity of one variant. The same rule for every channel."""

from __future__ import annotations

from typing import Any
from uuid import UUID


def tracks_stock(record: Any) -> bool:
    """Services set tracks_stock=false and never decrement units (ADR-015)."""
    raw = record.attributes.get("tracks_stock", True)
    if isinstance(raw, str):
        return raw.strip().lower() not in {"0", "false", "no"}
    return bool(raw)


def consume_stock(store, tenant_id: UUID, variant_sku: str, quantity: int, *, _expand: bool = True):
    """Subtract `quantity`. A combo subtracts its components and keeps its own stock at 0."""
    if quantity < 1:
        raise ValueError("bad_quantity")
    record = store.get_variant(tenant_id, variant_sku)
    if record is None:
        raise ValueError("unknown_variant")
    if _expand:
        from factory_os.domain.combos import combo_components

        parts = combo_components(record)
        if parts:
            for sku, each in parts:
                consume_stock(store, tenant_id, sku, each * quantity, _expand=False)
            return record
    if not tracks_stock(record):
        if record.attributes.get("disabled"):
            raise ValueError("out_of_stock")
        return record
    if record.attributes.get("disabled") or record.stock < quantity:
        raise ValueError("out_of_stock")
    remaining = record.stock - quantity
    if remaining == 0:
        return store.set_variant_availability(tenant_id, variant_sku, available=False)
    return store.set_variant_availability(
        tenant_id, variant_sku, available=True, stock=remaining
    )


def release_stock(store, tenant_id: UUID, variant_sku: str, quantity: int, *, _expand: bool = True):
    """Return units held by an open counter tab. A combo returns its components."""
    if quantity < 1:
        raise ValueError("bad_quantity")
    record = store.get_variant(tenant_id, variant_sku)
    if record is None:
        raise ValueError("unknown_variant")
    if _expand:
        from factory_os.domain.combos import combo_components

        parts = combo_components(record)
        if parts:
            for sku, each in parts:
                release_stock(store, tenant_id, sku, each * quantity, _expand=False)
            return record
    if not tracks_stock(record):
        return record
    return store.set_variant_availability(
        tenant_id, variant_sku, available=True, stock=record.stock + quantity
    )
