"""Agent orders for a later day. Today's stock stays until that date."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from factory_os.domain.combos import combo_components, makeable_units
from factory_os.domain.stock import consume_stock

BUSINESS_ZONE = ZoneInfo("America/La_Paz")


def business_today(now: datetime | None = None) -> date:
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(BUSINESS_ZONE).date()


def parse_fulfill_on(raw: object, *, today: date) -> date | None:
    """A date after today schedules the order. Today or empty stays a normal sale."""
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError("bad_date") from exc
    if parsed <= today:
        return None
    return parsed


def owner_notice(order) -> str:
    when = order.fulfill_on.isoformat() if order.fulfill_on else ""
    lines = ", ".join(f"{item.quantity}× {item.name}" for item in order.items)
    return f"Pedido para el {when}. Prepará: {lines}. No se restó el stock de hoy."


def _can_apply(store, tenant_id: UUID, order) -> bool:
    for item in order.items:
        record = store.get_variant(tenant_id, item.variant_sku)
        if record is None:
            return False
        if combo_components(record):
            if makeable_units(store, tenant_id, record, set()) < item.quantity:
                return False
            continue
        if record.attributes.get("disabled") or record.stock < item.quantity:
            return False
    return bool(order.items)


def apply_due_future_orders(store, tenant_id: UUID, *, on: date | None = None) -> int:
    """Decrement stock for agent orders whose day has arrived. One time each."""
    store.require_tenant(tenant_id)
    today = on or business_today()
    applied = 0
    for order in list(store.list_orders(tenant_id)):
        when = getattr(order, "fulfill_on", None)
        if when is None or when > today:
            continue
        if getattr(order, "stock_applied", False) or order.status == "cancelled":
            continue
        if getattr(order, "origin", "agent") == "counter":
            continue
        if not _can_apply(store, tenant_id, order):
            continue
        for item in order.items:
            consume_stock(store, tenant_id, item.variant_sku, item.quantity)
        store.mark_order_stock_applied(tenant_id, order.id)
        applied += 1
    return applied
