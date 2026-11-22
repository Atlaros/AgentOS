"""A combo is a catalog product. Stock lives on its components, not on the combo."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from factory_os.domain.catalog import tokenize
from factory_os.domain.store import VariantRecord


def combo_components(record: VariantRecord | None) -> list[tuple[str, int]]:
    """Component sku and quantity for one combo. Empty when this is a normal product."""
    if record is None:
        return []
    raw = record.attributes.get("combo_components")
    if not isinstance(raw, list):
        return []
    parts: list[tuple[str, int]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        sku = str(item.get("variant_sku") or "").strip()
        try:
            quantity = int(item.get("quantity") or 0)
        except (TypeError, ValueError):
            continue
        if sku and quantity > 0:
            parts.append((sku, quantity))
    return parts


def is_combo(record: VariantRecord | None) -> bool:
    return bool(combo_components(record))


def makeable_units(store, tenant_id: UUID, record: VariantRecord, held: set[str]) -> int:
    """How many of this combo fit in component stock. A held component blocks the combo."""
    parts = combo_components(record)
    if not parts:
        return record.stock
    counts: list[int] = []
    for sku, each in parts:
        if sku in held:
            return 0
        part = store.get_variant(tenant_id, sku)
        if part is None or part.attributes.get("disabled"):
            return 0
        counts.append(part.stock // each)
    return min(counts) if counts else 0


def _price(raw: str) -> Decimal:
    try:
        amount = Decimal(str(raw).strip().replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("bad_price") from exc
    if amount <= 0:
        raise ValueError("bad_price")
    return amount.quantize(Decimal("0.01"))


def _event_date(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("bad_date") from exc
    return text


def _checked_components(store, tenant_id: UUID, combo_sku: str, raw: list) -> list[tuple[str, int]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("bad_combo")
    merged: dict[str, int] = {}
    order: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            sku = str(item.get("variant_sku") or "").strip()
            try:
                quantity = int(item.get("quantity") or 0)
            except (TypeError, ValueError) as exc:
                raise ValueError("bad_combo") from exc
        else:
            raise ValueError("bad_combo")
        if not sku or quantity < 1 or sku == combo_sku:
            raise ValueError("bad_combo")
        if sku not in merged:
            order.append(sku)
        merged[sku] = merged.get(sku, 0) + quantity
    parts = [(sku, merged[sku]) for sku in order]
    for sku, _quantity in parts:
        component = store.get_variant(tenant_id, sku)
        if component is None:
            raise ValueError("unknown_variant")
        if is_combo(component):
            raise ValueError("bad_combo")
    return parts


def _record(
    *,
    sku: str,
    name: str,
    description: str,
    category: str,
    price: Decimal,
    currency: str,
    attributes: dict,
    supplier_id,
    reorder_threshold: int,
) -> VariantRecord:
    return VariantRecord(
        product_sku=sku,
        variant_sku=sku,
        name=name,
        description=description,
        category=category,
        attributes=attributes,
        price=price,
        currency=currency,
        stock=0,
        tokens=tokenize(" ".join([name, description, sku, category])),
        supplier_id=supplier_id,
        reorder_threshold=reorder_threshold,
    )


def create_combo(
    store,
    tenant_id: UUID,
    *,
    codigo: str,
    name: str,
    price: str,
    category: str = "Combos",
    components: list | None = None,
    event_date: str = "",
    currency: str = "BOB",
) -> VariantRecord:
    """Create a combo product. Its own stock stays 0."""
    sku = "".join((codigo or "").lower().split())
    label = (name or "").strip()
    if not sku or not label:
        raise ValueError("codigo_and_name_required")
    if store.get_variant(tenant_id, sku) is not None:
        raise ValueError("combo_exists")
    amount = _price(price)
    when = _event_date(event_date)
    parts = _checked_components(store, tenant_id, sku, components or [])
    group = (category or "Combos").strip() or "Combos"
    attributes: dict = {
        "codigo": sku,
        "category": group,
        "combo_components": [{"variant_sku": part, "quantity": qty} for part, qty in parts],
    }
    if when:
        attributes["event_date"] = when
    record = _record(
        sku=sku,
        name=label,
        description="",
        category=group,
        price=amount,
        currency=(currency or "BOB").strip() or "BOB",
        attributes=attributes,
        supplier_id=None,
        reorder_threshold=1,
    )
    return store.put_variant(tenant_id, record)


def update_combo(
    store,
    tenant_id: UUID,
    variant_sku: str,
    *,
    name: str | None = None,
    price: str | None = None,
    category: str | None = None,
    components: list | None = None,
    event_date: str | None = None,
) -> VariantRecord:
    """Change a combo. Price and components stay behind the supervisor PIN at the API."""
    sku = (variant_sku or "").strip()
    existing = store.get_variant(tenant_id, sku)
    if existing is None or not is_combo(existing):
        raise ValueError("unknown_variant")
    label = existing.name if name is None else name.strip()
    if not label:
        raise ValueError("bad_name")
    amount = existing.price if price is None else _price(price)
    group = existing.category if category is None else (category.strip() or "Combos")
    attributes = dict(existing.attributes)
    if components is not None:
        parts = _checked_components(store, tenant_id, sku, components)
        attributes["combo_components"] = [
            {"variant_sku": part, "quantity": qty} for part, qty in parts
        ]
    if event_date is not None:
        when = _event_date(event_date)
        if when:
            attributes["event_date"] = when
        else:
            attributes.pop("event_date", None)
    attributes["category"] = group
    record = _record(
        sku=sku,
        name=label,
        description=existing.description,
        category=group,
        price=Decimal(amount).quantize(Decimal("0.01")),
        currency=existing.currency or "BOB",
        attributes=attributes,
        supplier_id=existing.supplier_id,
        reorder_threshold=existing.reorder_threshold,
    )
    return store.put_variant(tenant_id, record)


def combo_payload(record: VariantRecord) -> dict[str, object]:
    price = Decimal(record.price).quantize(Decimal("0.01"))
    return {
        "variant_sku": record.variant_sku,
        "name": record.name,
        "price": f"{price:.2f}",
        "currency": record.currency or "BOB",
        "stock": record.stock,
        "category": record.category,
        "event_date": str(record.attributes.get("event_date") or ""),
        "components": list(record.attributes.get("combo_components") or []),
    }
