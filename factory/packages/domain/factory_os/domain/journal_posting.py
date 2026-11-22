"""Automatic journal posting from operational facts (ADR-011)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from factory_os.domain.chart_accounts import ensure_chart_seed
from factory_os.domain.journal_cogs import (
    post_cogs_for_ticket,
    reverse_cogs_for_movement,
)
from factory_os.domain.models import CashMovement, JournalEntry, Payment, PaymentStatus, PurchaseReceipt
from factory_os.domain.store import CommerceStore

_CAJA = "1100"
_BANCO = "1200"
_INVENTARIO = "1300"
_CXP = "2100"
_VENTAS = "4100"
_GASTOS = "5100"
_RETIROS = "5200"

_DRAW_MARKERS = ("retiro", "owner", "dueno")


def _normalize_category(raw: str) -> str:
    text = (raw or "").strip().lower()
    return (
        text.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )


def cash_out_account_code(category: str) -> str:
    """Map cash-out category to expense (5100) or owner draw (5200)."""
    cat = _normalize_category(category)
    if any(marker in cat for marker in _DRAW_MARKERS):
        return _RETIROS
    return _GASTOS


def _is_supplier_settlement(category: str) -> bool:
    """Cash leaving the drawer to settle CxP, not an operating expense."""
    return _normalize_category(category) in {"proveedor", "supplier"}


def _pair(
    debit_code: str,
    credit_code: str,
    amount: Decimal,
    currency: str,
) -> list[dict[str, Any]]:
    money = Decimal(str(amount))
    curr = (currency or "BOB").strip() or "BOB"
    return [
        {"account_code": debit_code, "direction": "debit", "amount": money, "currency": curr},
        {"account_code": credit_code, "direction": "credit", "amount": money, "currency": curr},
    ]


def _swap_lines(lines: list[Any]) -> list[dict[str, Any]]:
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


def post_cash_movement(store: CommerceStore, movement: CashMovement) -> JournalEntry:
    """Post balanced journal for a cash movement (idempotent kind=post)."""
    ensure_chart_seed(store, movement.tenant_id)
    existing = store.get_journal_by_origin(movement.tenant_id, "cash", movement.id, "post")
    if existing is not None:
        return existing
    currency = movement.currency or "BOB"
    amount = Decimal(str(movement.amount))
    if movement.direction == "in":
        lines = _pair(_CAJA, _VENTAS, amount, currency)
        memo = f"caja in {movement.category or 'venta'}".strip()
    elif _is_supplier_settlement(movement.category):
        lines = _pair(_CXP, _CAJA, amount, currency)
        memo = f"caja out {movement.category or 'proveedor'}".strip()
    else:
        lines = _pair(cash_out_account_code(movement.category), _CAJA, amount, currency)
        memo = f"caja out {movement.category or 'gasto'}".strip()
    return store.add_journal_entry(
        movement.tenant_id,
        entry_at=_entry_at(movement.created_at),
        origin_source="cash",
        origin_id=movement.id,
        kind="post",
        memo=memo,
        lines=lines,
    )


def reverse_cash_movement(store: CommerceStore, movement: CashMovement) -> JournalEntry:
    """Create reverse journal mirroring the cash post (idempotent kind=reverse)."""
    ensure_chart_seed(store, movement.tenant_id)
    post = store.get_journal_by_origin(movement.tenant_id, "cash", movement.id, "post")
    if post is None:
        post = post_cash_movement(store, movement)
    existing = store.get_journal_by_origin(movement.tenant_id, "cash", movement.id, "reverse")
    if existing is not None:
        reverse_cogs_for_movement(store, movement)
        return existing
    if not post.lines:
        post = store.get_journal_by_origin(movement.tenant_id, "cash", movement.id, "post")
        assert post is not None
    reverse = store.add_journal_entry(
        movement.tenant_id,
        entry_at=_entry_at(getattr(movement, "voided_at", None) or movement.created_at),
        origin_source="cash",
        origin_id=movement.id,
        kind="reverse",
        memo=f"reverso caja {movement.id}",
        lines=_swap_lines(post.lines),
        reverses_entry_id=post.id,
    )
    reverse_cogs_for_movement(store, movement)
    return reverse


def post_payment(store: CommerceStore, payment: Payment) -> JournalEntry | None:
    """Post Banco/Ventas for confirmed non-cash payments; skip provider=cash."""
    if payment.status is not PaymentStatus.CONFIRMED:
        return None
    if str(payment.provider or "").strip().lower() == "cash":
        return None
    ensure_chart_seed(store, payment.tenant_id)
    existing = store.get_journal_by_origin(payment.tenant_id, "payment", payment.id, "post")
    if existing is not None:
        _maybe_post_walkin_cogs(store, payment)
        return existing
    entry = store.add_journal_entry(
        payment.tenant_id,
        entry_at=_entry_at(payment.created_at),
        origin_source="payment",
        origin_id=payment.id,
        kind="post",
        memo=f"pago {payment.provider}",
        lines=_pair(_BANCO, _VENTAS, Decimal(str(payment.amount)), payment.currency or "BOB"),
    )
    _maybe_post_walkin_cogs(store, payment)
    return entry


def _maybe_post_walkin_cogs(store: CommerceStore, payment: Payment) -> None:
    ticket_fn = getattr(store, "cash_sale_ticket_for_payment", None)
    if not callable(ticket_fn) or payment.id is None:
        return
    ticket = ticket_fn(payment.tenant_id, payment.id)
    if ticket is None:
        return
    post_cogs_for_ticket(store, ticket)


def post_purchase(store: CommerceStore, receipt: PurchaseReceipt) -> JournalEntry:
    """Post Inventario vs Caja (cash) or CxP 2100 (credit)."""
    ensure_chart_seed(store, receipt.tenant_id)
    existing = store.get_journal_by_origin(receipt.tenant_id, "purchase", receipt.id, "post")
    if existing is not None:
        return existing
    amount = (receipt.unit_cost * receipt.quantity).quantize(Decimal("0.01"))
    method = (getattr(receipt, "payment_method", None) or "cash").strip().lower() or "cash"
    credit_code = _CXP if method == "credit" else _CAJA
    stamp = getattr(receipt, "received_at", None) or receipt.created_at
    return store.add_journal_entry(
        receipt.tenant_id,
        entry_at=_entry_at(stamp),
        origin_source="purchase",
        origin_id=receipt.id,
        kind="post",
        memo=f"compra {receipt.variant_sku}",
        lines=_pair(_INVENTARIO, credit_code, amount, receipt.currency or "BOB"),
    )


def post_supplier_payment(
    store: CommerceStore,
    tenant_id: UUID,
    *,
    origin_id: UUID,
    amount: Decimal,
    currency: str = "BOB",
    method: str = "transfer",
    memo: str = "",
    entry_at: datetime | None = None,
) -> JournalEntry:
    """Settle CxP: debit 2100, credit Caja (cash) or Banco (transfer). No IVA."""
    ensure_chart_seed(store, tenant_id)
    existing = store.get_journal_by_origin(tenant_id, "supplier_payment", origin_id, "post")
    if existing is not None:
        return existing
    method_clean = (method or "transfer").strip().lower() or "transfer"
    credit_code = _CAJA if method_clean == "cash" else _BANCO
    money = Decimal(str(amount)).quantize(Decimal("0.01"))
    return store.add_journal_entry(
        tenant_id,
        entry_at=_entry_at(entry_at),
        origin_source="supplier_payment",
        origin_id=origin_id,
        kind="post",
        memo=(memo or f"pago proveedor {method_clean}").strip(),
        lines=_pair(_CXP, credit_code, money, currency or "BOB"),
    )


def sync_journal(store: CommerceStore, tenant_id: UUID) -> None:
    """Backfill journal posts/reverses for existing operational facts."""
    store.require_tenant(tenant_id)
    ensure_chart_seed(store, tenant_id)
    for payment in store.list_payments(tenant_id):
        post_payment(store, payment)
    for movement in store.list_cash(tenant_id):
        status = (movement.status or "recorded").strip() or "recorded"
        if status == "voided":
            reverse_cash_movement(store, movement)
        else:
            post_cash_movement(store, movement)
    purchases = getattr(store, "purchases", None)
    if isinstance(purchases, list):
        for receipt in purchases:
            if getattr(receipt, "tenant_id", None) == tenant_id:
                post_purchase(store, receipt)
    list_fn = getattr(store, "list_purchases", None)
    if callable(list_fn):
        for receipt in list_fn(tenant_id):
            post_purchase(store, receipt)
    ticket_fn = getattr(store, "list_cash_sale_tickets", None)
    if callable(ticket_fn):
        for ticket in ticket_fn(tenant_id):
            status = (ticket.status or "").strip()
            if status == "recorded":
                post_cogs_for_ticket(store, ticket)
            elif status == "voided":
                from factory_os.domain.journal_cogs import reverse_cogs_for_sale

                reverse_cogs_for_sale(store, tenant_id, ticket.id, entry_at=ticket.created_at)
