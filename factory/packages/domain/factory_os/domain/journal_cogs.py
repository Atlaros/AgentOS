"""COGS posting from weighted-average purchase cost (ADR-011 Fase 3)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence
from uuid import UUID

from factory_os.domain.chart_accounts import ensure_chart_seed
from factory_os.domain.models import CashMovement, CashSaleTicket, JournalEntry, PurchaseReceipt
from factory_os.domain.store import CommerceStore

_INVENTARIO = "1300"
_COGS = "5110"


def weighted_avg_unit_cost(
    store: CommerceStore,
    tenant_id: UUID,
    variant_sku: str,
) -> Decimal | None:
    """Qty-weighted average unit cost from purchase receipts. None when no purchases."""
    sku = (variant_sku or "").strip()
    if not sku:
        return None
    receipts = _list_purchases(store, tenant_id)
    total_qty = 0
    total_cost = Decimal("0")
    for receipt in receipts:
        if (receipt.variant_sku or "").strip() != sku:
            continue
        qty = int(receipt.quantity)
        if qty < 1:
            continue
        total_qty += qty
        total_cost += Decimal(str(receipt.unit_cost)) * qty
    if total_qty < 1:
        return None
    return (total_cost / Decimal(total_qty)).quantize(Decimal("0.0001"))


def _list_purchases(store: CommerceStore, tenant_id: UUID) -> list[PurchaseReceipt]:
    list_fn = getattr(store, "list_purchases", None)
    if callable(list_fn):
        return list(list_fn(tenant_id))
    purchases = getattr(store, "purchases", None)
    if isinstance(purchases, list):
        return [item for item in purchases if getattr(item, "tenant_id", None) == tenant_id]
    return []


def _pair(
    debit_code: str,
    credit_code: str,
    amount: Decimal,
    currency: str,
) -> list[dict[str, Any]]:
    money = Decimal(str(amount)).quantize(Decimal("0.01"))
    curr = (currency or "BOB").strip() or "BOB"
    return [
        {"account_code": debit_code, "direction": "debit", "amount": money, "currency": curr},
        {"account_code": credit_code, "direction": "credit", "amount": money, "currency": curr},
    ]


def _swap_lines(lines: Sequence[Any]) -> list[dict[str, Any]]:
    swapped: list[dict[str, Any]] = []
    for line in lines:
        direction = "credit" if str(line.direction) == "debit" else "debit"
        payload: dict[str, Any] = {
            "direction": direction,
            "amount": Decimal(str(line.amount)),
            "currency": (line.currency or "BOB"),
        }
        if getattr(line, "account_code", None):
            payload["account_code"] = line.account_code
        else:
            payload["account_id"] = line.account_id
        swapped.append(payload)
    return swapped


def _entry_at(stamp: datetime | None) -> datetime:
    return stamp or datetime.now(UTC)


def _line_specs(lines: Sequence[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in lines:
        if isinstance(line, Mapping):
            sku = str(line.get("variant_sku") or "").strip()
            qty = int(line.get("quantity") or 0)
        else:
            sku = str(getattr(line, "variant_sku", "") or "").strip()
            qty = int(getattr(line, "quantity", 0) or 0)
        if sku and qty > 0:
            out.append({"variant_sku": sku, "quantity": qty})
    return out


def post_cogs_for_sale(
    store: CommerceStore,
    tenant_id: UUID,
    origin_source: str,
    origin_id: UUID,
    lines: Sequence[Any],
    *,
    currency: str = "BOB",
    entry_at: datetime | None = None,
) -> JournalEntry | None:
    """Debit 5110 / Credit 1300 for known costs. Skips SKUs without purchase cost."""
    _ = origin_source  # sale context for callers; journal origin is always cogs+sale_id
    ensure_chart_seed(store, tenant_id)
    existing = store.get_journal_by_origin(tenant_id, "cogs", origin_id, "post")
    if existing is not None:
        return existing

    total = Decimal("0")
    from factory_os.domain.combos import combo_components

    cost_lines: list[dict[str, object]] = []
    for spec in _line_specs(lines):
        record = store.get_variant(tenant_id, spec["variant_sku"])
        parts = combo_components(record)
        if parts:
            for sku, each in parts:
                cost_lines.append({"variant_sku": sku, "quantity": each * int(spec["quantity"])})
        else:
            cost_lines.append(spec)
    for spec in cost_lines:
        unit = weighted_avg_unit_cost(store, tenant_id, str(spec["variant_sku"]))
        if unit is None:
            continue
        total += (unit * Decimal(spec["quantity"])).quantize(Decimal("0.01"))
    total = total.quantize(Decimal("0.01"))
    if total <= 0:
        return None

    return store.add_journal_entry(
        tenant_id,
        entry_at=_entry_at(entry_at),
        origin_source="cogs",
        origin_id=origin_id,
        kind="post",
        memo=f"cogs sale {origin_id}",
        lines=_pair(_COGS, _INVENTARIO, total, currency),
    )


def reverse_cogs_for_sale(
    store: CommerceStore,
    tenant_id: UUID,
    origin_id: UUID,
    *,
    entry_at: datetime | None = None,
) -> JournalEntry | None:
    """Reverse COGS post for a sale (idempotent). No-op when no post exists."""
    ensure_chart_seed(store, tenant_id)
    post = store.get_journal_by_origin(tenant_id, "cogs", origin_id, "post")
    if post is None:
        return None
    existing = store.get_journal_by_origin(tenant_id, "cogs", origin_id, "reverse")
    if existing is not None:
        return existing
    if not post.lines:
        post = store.get_journal_by_origin(tenant_id, "cogs", origin_id, "post")
        assert post is not None
    return store.add_journal_entry(
        tenant_id,
        entry_at=_entry_at(entry_at),
        origin_source="cogs",
        origin_id=origin_id,
        kind="reverse",
        memo=f"reverso cogs {origin_id}",
        lines=_swap_lines(post.lines),
        reverses_entry_id=post.id,
    )


def post_cogs_for_ticket(store: CommerceStore, ticket: CashSaleTicket) -> JournalEntry | None:
    """Post COGS for a recorded walk-in ticket."""
    if (ticket.status or "").strip() not in {"recorded", ""}:
        return None
    return post_cogs_for_sale(
        store,
        ticket.tenant_id,
        "sale",
        ticket.id,
        ticket.lines,
        currency=ticket.currency or "BOB",
        entry_at=ticket.created_at,
    )


def reverse_cogs_for_movement(store: CommerceStore, movement: CashMovement) -> JournalEntry | None:
    """When a cash movement linked to a ticket is voided, reverse its COGS."""
    ticket_id = getattr(movement, "ticket_id", None)
    if ticket_id is None:
        return None
    return reverse_cogs_for_sale(
        store,
        movement.tenant_id,
        ticket_id,
        entry_at=getattr(movement, "voided_at", None) or movement.created_at,
    )
