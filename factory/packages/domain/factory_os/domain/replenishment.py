"""Replenishment grouping for Proveedores (ADR-012 T3)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from factory_os.domain.purchase_orders import (
    HEURISTIC_NOTE,
    IN_TRANSIT_STATUSES,
    suggested_qty,
)
from factory_os.domain.suppliers import list_low_stock


def build_replenishment(store: Any, tenant_id: UUID) -> dict[str, Any]:
    """Group low-stock variants by preferred supplier with suggested quantities."""
    low = list_low_stock(store)
    sold_map: dict[str, int] = {}
    try:
        sold_map = dict(store.sold_units_by_sku(tenant_id) or {})
    except Exception:
        sold_map = {}

    supplier_names: dict[str, str] = {}
    try:
        for supplier in store.list_suppliers(tenant_id, active_only=False):
            supplier_names[str(supplier.id)] = supplier.name
    except Exception:
        supplier_names = {}

    buckets: dict[str | None, list[dict[str, Any]]] = {}
    sin_stock = 0
    stock_bajo = 0
    for record in low:
        stock = int(record.stock)
        threshold = int(getattr(record, "reorder_threshold", 1) or 1)
        if stock <= 0:
            sin_stock += 1
        else:
            stock_bajo += 1
        sold_proxy = int(sold_map.get(record.variant_sku, 0) or 0)
        qty = suggested_qty(
            stock=stock, reorder_threshold=threshold, sold_proxy=sold_proxy
        )
        sid = record.supplier_id
        key: str | None = str(sid) if sid else None
        from factory_os.domain.media import primary_media_fields

        media_id, thumb_url = primary_media_fields(
            store,
            tenant_id,
            record.product_sku,
            attrs=dict(record.attributes or {}),
        )
        buckets.setdefault(key, []).append(
            {
                "variant_sku": record.variant_sku,
                "name": record.name,
                "codigo": str(record.attributes.get("codigo") or ""),
                "stock": stock,
                "reorder_threshold": threshold,
                "sold_proxy": sold_proxy,
                "ventas": sold_proxy,
                "suggested_qty": qty,
                "supplier_id": key,
                "media_id": media_id,
                "thumb_url": thumb_url,
                "image_url": str(record.attributes.get("image_url") or ""),
            }
        )

    def _item_sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        # Stock 0 first, then higher sold, then sku.
        stock = int(item["stock"])
        sold = int(item.get("sold_proxy") or 0)
        return (0 if stock <= 0 else 1, -sold, str(item["variant_sku"]))

    groups: list[dict[str, Any]] = []
    # Named suppliers first (alpha), then "sin proveedor".
    named_keys = sorted(
        (k for k in buckets if k is not None),
        key=lambda k: (supplier_names.get(k) or k).lower(),
    )
    ordered_keys: list[str | None] = list(named_keys)
    if None in buckets:
        ordered_keys.append(None)

    for key in ordered_keys:
        items = sorted(buckets[key], key=_item_sort_key)
        if key is None:
            groups.append(
                {
                    "supplier_id": None,
                    "supplier_name": "Sin proveedor",
                    "items": items,
                }
            )
        else:
            groups.append(
                {
                    "supplier_id": key,
                    "supplier_name": supplier_names.get(key) or "Proveedor",
                    "items": items,
                }
            )

    in_transit = 0
    try:
        for order in store.list_purchase_orders(tenant_id, status=None):
            if order.status in IN_TRANSIT_STATUSES:
                in_transit += 1
    except Exception:
        in_transit = 0

    return {
        "cards": {
            "sin_stock": sin_stock,
            "stock_bajo": stock_bajo,
            "ordenes_en_camino": in_transit,
        },
        "groups": groups,
        "heuristic_note": HEURISTIC_NOTE,
    }
