"""Purchase orders (ADR-012): draft create, send/cancel, receive, and supplier payment."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from factory_os.domain.models import PurchaseOrder, PurchaseOrderLine

PO_STATUSES = frozenset(
    {"draft", "sent", "partially_received", "received", "cancelled"}
)
IN_TRANSIT_STATUSES = frozenset({"sent", "partially_received"})
RECEIVABLE_STATUSES = frozenset({"sent", "partially_received"})
# Receiving statuses are set by receive_purchase_order, not by an arbitrary PATCH.
ALLOWED_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"sent", "cancelled"}),
    "sent": frozenset({"cancelled"}),
}

HEURISTIC_NOTE = (
    "suggested_qty = max(1, deficit + 1 + min(sold_proxy, 10)) where "
    "deficit = max(0, reorder_threshold - stock). sold_proxy is all-time "
    "confirmed sales (proxy for ~30d). Editable in UI; not an optimal EOQ."
)


def suggested_qty(*, stock: int, reorder_threshold: int, sold_proxy: int = 0) -> int:
    """Simple replenishment heuristic — not optimal inventory math."""
    deficit = max(0, int(reorder_threshold) - int(stock))
    sold_bump = min(max(0, int(sold_proxy)), 10)
    return max(1, deficit + 1 + sold_bump)


def public_number(order_id: UUID) -> str:
    return f"PO-{str(order_id).replace('-', '')[:8].upper()}"


def purchase_order_line_public(line: PurchaseOrderLine) -> dict[str, Any]:
    return {
        "id": str(line.id),
        "variant_sku": line.variant_sku,
        "quantity_ordered": int(line.quantity_ordered),
        "quantity_received": int(line.quantity_received),
        "unit_cost": str(line.unit_cost) if line.unit_cost is not None else None,
        "currency": line.currency,
    }


def purchase_order_public(order: PurchaseOrder, *, include_lines: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(order.id),
        "number": public_number(order.id),
        "supplier_id": str(order.supplier_id),
        "status": order.status,
        "payment_status": order.payment_status or "unpaid",
        "amount_paid": str(_money(order.amount_paid)),
        "notes": order.notes,
        "line_count": len(order.lines),
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
    }
    if include_lines:
        payload["lines"] = [purchase_order_line_public(line) for line in order.lines]
    return payload


def create_draft_purchase_order(
    store: Any,
    tenant_id: UUID,
    supplier_id: UUID,
    lines: list[dict[str, Any]],
    *,
    notes: str = "",
) -> PurchaseOrder:
    """Create a draft PO. Supplier required; lines non-empty with quantity > 0."""
    if supplier_id is None:
        raise ValueError("supplier_required")
    if not lines:
        raise ValueError("empty_lines")
    normalized: list[dict[str, Any]] = []
    for raw in lines:
        sku = str(raw.get("variant_sku") or "").strip()
        qty = int(raw.get("quantity") or raw.get("quantity_ordered") or 0)
        if not sku:
            raise ValueError("bad_line")
        if qty < 1:
            raise ValueError("bad_quantity")
        unit_cost = raw.get("unit_cost")
        cost: Decimal | None = None
        if unit_cost is not None and str(unit_cost).strip() != "":
            cost = Decimal(str(unit_cost).replace(",", "."))
            if cost < 0:
                raise ValueError("bad_unit_cost")
        currency = str(raw.get("currency") or "BOB").strip() or "BOB"
        if store.get_variant(tenant_id, sku) is None:
            raise KeyError(sku)
        normalized.append(
            {
                "variant_sku": sku,
                "quantity": qty,
                "unit_cost": cost,
                "currency": currency,
            }
        )
    if store.get_supplier(tenant_id, supplier_id) is None:
        raise KeyError(supplier_id)
    return store.create_purchase_order(
        tenant_id,
        supplier_id,
        normalized,
        status="draft",
        notes=notes or "",
    )


def list_purchase_orders(
    store: Any, tenant_id: UUID, *, status: str | None = None
) -> list[PurchaseOrder]:
    return store.list_purchase_orders(tenant_id, status=status)


def get_purchase_order(store: Any, tenant_id: UUID, order_id: UUID) -> PurchaseOrder | None:
    return store.get_purchase_order(tenant_id, order_id)


def _money(value: Decimal | int | str | None) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def derive_payment_status(amount_paid: Decimal, received_value: Decimal) -> str:
    paid = _money(amount_paid)
    received = _money(received_value)
    if paid <= 0:
        return "unpaid"
    if received > 0 and paid >= received:
        return "paid"
    return "partial"


def order_received_value(order: PurchaseOrder, store: Any | None = None) -> Decimal:
    """Value already received. Prefer linked receipts so mixed unit costs stay exact."""
    if store is not None:
        receipts = [
            item
            for item in store.list_purchases(order.tenant_id)
            if getattr(item, "purchase_order_id", None) == order.id
        ]
        if receipts:
            total = Decimal("0")
            for item in receipts:
                total += Decimal(str(item.unit_cost)) * int(item.quantity)
            return _money(total)
    total = Decimal("0")
    for line in order.lines:
        if line.quantity_received <= 0 or line.unit_cost is None:
            continue
        total += Decimal(str(line.unit_cost)) * line.quantity_received
    return _money(total)


def transition_purchase_order(
    store: Any, tenant_id: UUID, order_id: UUID, new_status: str
) -> PurchaseOrder:
    """Move a PO along the allowed graph. Receive statuses are not patched here."""
    order = store.get_purchase_order(tenant_id, order_id)
    if order is None:
        raise KeyError(order_id)
    target = (new_status or "").strip().lower()
    allowed = ALLOWED_STATUS_TRANSITIONS.get(order.status, frozenset())
    if target not in allowed:
        raise ValueError("bad_status")
    return store.set_purchase_order_status(tenant_id, order_id, target)


def _line_cost(raw: dict[str, Any], line: PurchaseOrderLine) -> Decimal:
    supplied = raw.get("unit_cost")
    if supplied is not None and str(supplied).strip() != "":
        cost = Decimal(str(supplied).replace(",", "."))
    elif line.unit_cost is not None:
        cost = Decimal(str(line.unit_cost))
    else:
        raise ValueError("bad_unit_cost")
    if cost <= 0:
        raise ValueError("bad_unit_cost")
    return cost


def receive_purchase_order(
    store: Any,
    tenant_id: UUID,
    order_id: UUID,
    lines: list[dict[str, Any]],
    payment_method: str = "cash",
) -> PurchaseOrder:
    """Receive against a sent or partial PO. Stock and journal happen inside receive_purchase."""
    order = store.get_purchase_order(tenant_id, order_id)
    if order is None:
        raise KeyError(order_id)
    if order.status not in RECEIVABLE_STATUSES:
        raise ValueError("bad_status")
    method = (payment_method or "cash").strip().lower() or "cash"
    if method not in {"cash", "credit"}:
        raise ValueError("bad_payment_method")
    if not lines:
        raise ValueError("empty_lines")

    by_sku = {line.variant_sku: line for line in order.lines}
    pending: dict[UUID, int] = {}
    prepared: list[tuple[PurchaseOrderLine, int, Decimal, str]] = []
    for raw in lines:
        sku = str(raw.get("variant_sku") or "").strip()
        qty = int(raw.get("quantity") or 0)
        if not sku:
            raise ValueError("bad_line")
        if qty < 1:
            raise ValueError("bad_quantity")
        line = by_sku.get(sku)
        if line is None:
            raise ValueError("bad_line")
        already = pending.get(line.id, 0)
        remaining = line.quantity_ordered - line.quantity_received - already
        if qty > remaining:
            raise ValueError("over_receive")
        cost = _line_cost(raw, line)
        currency = str(raw.get("currency") or line.currency or "BOB").strip() or "BOB"
        pending[line.id] = already + qty
        prepared.append((line, qty, cost, currency))

    base_received = {line.id: line.quantity_received for line in order.lines}
    applied: dict[UUID, int] = {}
    cash_added = Decimal("0")
    for line, qty, cost, currency in prepared:
        store.receive_purchase(
            tenant_id,
            line.variant_sku,
            qty,
            cost,
            currency,
            payment_method=method,
            supplier_id=order.supplier_id,
            purchase_order_id=order.id,
        )
        applied[line.id] = applied.get(line.id, 0) + qty
        store.set_purchase_order_line_received(
            tenant_id,
            order.id,
            line.id,
            base_received[line.id] + applied[line.id],
            unit_cost=cost,
        )
        if method == "cash":
            cash_added += _money(cost * qty)

    refreshed = store.get_purchase_order(tenant_id, order_id)
    if refreshed is None:
        raise KeyError(order_id)
    complete = all(
        line.quantity_received >= line.quantity_ordered for line in refreshed.lines
    )
    new_status = "received" if complete else "partially_received"
    store.set_purchase_order_status(tenant_id, order_id, new_status)
    amount_paid = _money(refreshed.amount_paid)
    if method == "cash" and cash_added > 0:
        amount_paid = _money(amount_paid + cash_added)
    received_value = order_received_value(refreshed, store)
    payment_status = derive_payment_status(amount_paid, received_value)
    return store.set_purchase_order_payment(
        tenant_id,
        order_id,
        payment_status=payment_status,
        amount_paid=amount_paid,
    )


def register_supplier_payment(
    store: Any,
    tenant_id: UUID,
    order_id: UUID,
    *,
    amount: Decimal,
    method: str,
    currency: str = "BOB",
) -> PurchaseOrder:
    """Settle unpaid credit. Cash hits the drawer as CxP/Caja. Transfer is Banco/CxP only."""
    order = store.get_purchase_order(tenant_id, order_id)
    if order is None:
        raise KeyError(order_id)
    received_value = order_received_value(order, store)
    exposure = _money(received_value - _money(order.amount_paid))
    if exposure <= 0:
        raise ValueError("nothing_to_pay")
    money = _money(amount)
    if money <= 0 or money > exposure:
        raise ValueError("bad_amount")
    method_clean = (method or "").strip().lower()
    if method_clean not in {"cash", "transfer"}:
        raise ValueError("bad_payment_method")
    curr = (currency or "BOB").strip() or "BOB"
    memo = f"pago proveedor {public_number(order.id)}"
    if method_clean == "cash":
        store.record_cash(
            tenant_id,
            "out",
            money,
            curr,
            memo,
            category="proveedor",
            method="cash",
        )
    else:
        from factory_os.domain.journal_posting import post_supplier_payment

        post_supplier_payment(
            store,
            tenant_id,
            origin_id=uuid4(),
            amount=money,
            currency=curr,
            method="transfer",
            memo=memo,
        )
    amount_paid = _money(_money(order.amount_paid) + money)
    payment_status = derive_payment_status(amount_paid, received_value)
    return store.set_purchase_order_payment(
        tenant_id,
        order_id,
        payment_status=payment_status,
        amount_paid=amount_paid,
    )
