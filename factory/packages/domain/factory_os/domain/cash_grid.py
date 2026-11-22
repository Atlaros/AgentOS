"""Touch-grid catalog. Sold-out stays visible. The price is the catalog price."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from factory_os.domain.cash_sales import _parse_exact_price
from factory_os.domain.catalog_categories import UNCATEGORIZED
from factory_os.domain.store import VariantRecord

_GRID_LIMIT = 200
BESTSELLERS = "Más vendidos"
_SOLD_STATUSES = frozenset({"placed", "delivered"})


def sold_units_by_product(store, tenant_id: UUID) -> dict[str, int]:
    """Units already sold: recorded counter tickets and confirmed chat orders.

    A counter sale has both a ticket and a counter order. The ticket is the sale.
    An open table and an unpaid chat reservation are not sold yet.
    """
    totals: dict[str, int] = {}

    def add(sku: str, quantity: int) -> None:
        if quantity < 1:
            return
        record = store.get_variant(tenant_id, sku)
        if record is None:
            return
        totals[record.product_sku] = totals.get(record.product_sku, 0) + quantity

    for ticket in store.list_cash_sale_tickets(tenant_id):
        if (ticket.status or "") != "recorded":
            continue
        for line in ticket.lines:
            add(line.variant_sku, int(line.quantity))
    for order in store.list_orders(tenant_id):
        if getattr(order, "origin", "agent") == "counter":
            continue
        if order.status not in _SOLD_STATUSES:
            continue
        for item in order.items:
            add(item.variant_sku, int(item.quantity))
    return totals


def _label(record: VariantRecord) -> str:
    name = (record.category or "").strip()
    return name or UNCATEGORIZED


def _matches(record: VariantRecord, query: str, price_q: Decimal | None) -> bool:
    if not query:
        return not bool(record.attributes.get("test_only"))
    haystack = " ".join(
        [
            record.name,
            record.description,
            record.product_sku,
            record.variant_sku,
            str(record.attributes.get("codigo") or ""),
            record.category or "",
        ]
    ).casefold()
    if query.casefold() in haystack:
        return True
    return price_q is not None and record.price == price_q


def _variant_payload(store, tenant_id: UUID, record: VariantRecord, *, held: set[str]) -> dict[str, Any]:
    from factory_os.domain.combos import is_combo, makeable_units

    from factory_os.domain.stock import tracks_stock

    if is_combo(record):
        stock = makeable_units(store, tenant_id, record, held)
        sold_out = bool(record.attributes.get("disabled")) or stock < 1
    elif not tracks_stock(record):
        stock = int(record.stock)
        sold_out = bool(record.attributes.get("disabled"))
    else:
        stock = record.stock
        sold_out = bool(record.attributes.get("disabled")) or record.stock < 1
    selectable = not sold_out and record.variant_sku not in held
    price = Decimal(record.price).quantize(Decimal("0.01"))
    return {
        "variant_sku": record.variant_sku,
        "name": record.name,
        "price": f"{price:.2f}",
        "currency": record.currency or "BOB",
        "stock": stock,
        "talla": str(record.attributes.get("talla") or ""),
        "color": str(record.attributes.get("color") or ""),
        "sold_out": sold_out,
        "selectable": selectable,
    }


def _product_payload(
    store,
    tenant_id: UUID,
    product_sku: str,
    variants: list[VariantRecord],
    *,
    held: set[str],
    sold_units: int = 0,
) -> dict[str, Any]:
    rows = sorted(
        variants,
        key=lambda record: (
            str(record.attributes.get("talla") or ""),
            str(record.attributes.get("color") or ""),
            record.variant_sku,
        ),
    )
    payload = [_variant_payload(store, tenant_id, record, held=held) for record in rows]
    selectable = [row for row in payload if row["selectable"]]
    prices = [Decimal(row["price"]) for row in (selectable or payload)]
    source = next((record for record in rows if record.variant_sku not in held and record.stock >= 1), rows[0])
    category = _label(source)
    for record in rows:
        if _label(record) != UNCATEGORIZED:
            category = _label(record)
            break
    image = next(
        (
            record.attributes
            for record in rows
            if record.attributes.get("thumb_path")
            or record.attributes.get("image_path")
            or record.attributes.get("image_url")
        ),
        rows[0].attributes,
    )
    from factory_os.domain.media import primary_media_fields

    media_id, thumb_url = primary_media_fields(
        store, tenant_id, product_sku, attrs=dict(image or {})
    )
    name = source.name or rows[0].name
    return {
        "product_sku": product_sku,
        "name": name,
        "category": category,
        "initial": (name.strip()[:1] or "?").upper(),
        "image_path": str(image.get("image_path") or ""),
        "thumb_path": str(image.get("thumb_path") or ""),
        "image_url": str(image.get("image_url") or ""),
        "media_id": media_id,
        "thumb_url": thumb_url,
        "price": f"{min(prices):.2f}",
        "currency": payload[0]["currency"],
        "sold_out": not selectable,
        "sold_units": int(sold_units),
        "variant_count": len(payload),
        "variants": payload,
    }


def build_cash_grid(
    store,
    tenant_id: UUID,
    *,
    query: str = "",
    category: str = "",
    limit: int = _GRID_LIMIT,
) -> list[dict[str, Any]]:
    """Group variants under their product. Sold-out stays on the grid and is not selectable."""
    store.require_tenant(tenant_id)
    from factory_os.domain.order_hold import release_expired_unpaid_orders

    release_expired_unpaid_orders(store, tenant_id)
    needle = (query or "").strip()
    price_q = _parse_exact_price(needle)
    wanted = (category or "").strip()
    if wanted.casefold() == "todo":
        wanted = ""
    held = set(store.held_variant_skus(tenant_id))
    sold = sold_units_by_product(store, tenant_id)
    bestsellers = wanted.casefold() == BESTSELLERS.casefold()
    if bestsellers:
        wanted = ""
    groups: dict[str, list[VariantRecord]] = {}
    for record in store.iter_variants():
        groups.setdefault(record.product_sku, []).append(record)
    order = store.category_sort_map(tenant_id) if hasattr(store, "category_sort_map") else {}
    products: list[dict[str, Any]] = []
    for product_sku, variants in groups.items():
        if needle and not any(_matches(record, needle, price_q) for record in variants):
            continue
        if not needle and all(record.attributes.get("test_only") for record in variants):
            continue
        if wanted and not any(_label(record).casefold() == wanted.casefold() for record in variants):
            continue
        products.append(
            _product_payload(
                store,
                tenant_id,
                product_sku,
                variants,
                held=held,
                sold_units=int(sold.get(product_sku, 0)),
            )
        )
    if bestsellers:
        products = [product for product in products if int(product["sold_units"]) > 0]
        products.sort(key=lambda product: (-int(product["sold_units"]), product["product_sku"]))
    else:
        products.sort(
            key=lambda product: (
                10001 if product["category"] == UNCATEGORIZED else int(order.get(product["category"], 1000)),
                product["product_sku"],
            )
        )
    return products[:limit]
