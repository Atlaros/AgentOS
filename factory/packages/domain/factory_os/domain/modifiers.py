"""Catalog extras. The cashier picks one. The server adds the price difference."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import UUID


@dataclass
class CatalogModifier:
    id: UUID
    tenant_id: UUID
    name: str
    price_delta: Decimal
    currency: str = "BOB"


def modifier_payload(row: CatalogModifier) -> dict[str, str]:
    delta = Decimal(row.price_delta).quantize(Decimal("0.01"))
    return {
        "id": str(row.id),
        "name": row.name,
        "price_delta": str(delta),
        "currency": row.currency or "BOB",
    }


def create_modifier(store, tenant_id: UUID, *, name: str, price_delta: str, currency: str = "BOB") -> CatalogModifier:
    clean = (name or "").strip()
    if not clean or len(clean) > 80:
        raise ValueError("bad_name")
    try:
        delta = Decimal(str(price_delta).strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("bad_price") from exc
    money = (currency or "BOB").strip() or "BOB"
    return store.create_modifier(
        tenant_id,
        name=clean,
        price_delta=delta,
        currency=money,
    )


def list_modifier_payloads(store, tenant_id: UUID) -> list[dict[str, str]]:
    rows = store.list_modifiers(tenant_id)
    return [modifier_payload(row) for row in rows]


def selected_options(store, tenant_id: UUID, option_ids: tuple[str, ...]) -> tuple[list[dict[str, str]], Decimal]:
    """Snapshot the chosen extras. Unknown ids do not invent a price."""
    chosen: list[dict[str, str]] = []
    total = Decimal("0.00")
    seen: set[str] = set()
    for raw in option_ids:
        key = (raw or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            modifier_id = UUID(key)
        except ValueError as exc:
            raise ValueError("unknown_modifier") from exc
        found = store.get_modifier(tenant_id, modifier_id)
        if found is None:
            raise ValueError("unknown_modifier")
        delta = Decimal(found.price_delta).quantize(Decimal("0.01"))
        chosen.append(
            {
                "id": str(found.id),
                "name": found.name,
                "price_delta": str(delta),
            }
        )
        total += delta
    return chosen, total.quantize(Decimal("0.01"))
