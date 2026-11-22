"""Operating ledger. Entries follow confirmed payments, cash, and received purchases.

An invoice document is not a source. Issuing one does not post and does not confirm a payment.
"""

from __future__ import annotations

from decimal import Decimal

from factory_os.domain.models import CashMovement, LedgerEntry, Payment, PaymentStatus, PurchaseReceipt
from factory_os.domain.store import CommerceStore

_RECORDED = "recorded"
_VOIDED = "voided"


def entry_is_recorded(entry: LedgerEntry) -> bool:
    """Missing or empty status counts as recorded (pre-028 rows)."""
    return (entry.status or _RECORDED) == _RECORDED


def recorded_entries(entries: list[LedgerEntry]) -> list[LedgerEntry]:
    return [entry for entry in entries if entry_is_recorded(entry)]


def sum_ledger(entries: list[LedgerEntry]) -> tuple[Decimal, Decimal, Decimal]:
    """Return (in, out, balance) for recorded entries only."""
    active = recorded_entries(entries)
    incoming = sum((item.amount for item in active if item.direction == "in"), Decimal("0"))
    outgoing = sum((item.amount for item in active if item.direction == "out"), Decimal("0"))
    return incoming, outgoing, incoming - outgoing


def remember_payment(store: CommerceStore, payment: Payment) -> LedgerEntry | None:
    if payment.status is not PaymentStatus.CONFIRMED:
        return None
    # Owner cash posts through record_cash / remember_cash so the drawer and
    # the ledger stay a single inflow. Baneco and other adapters post here.
    if str(payment.provider or "").strip().lower() == "cash":
        return None
    from factory_os.domain.journal_posting import post_payment

    entry = store.add_ledger_entry(
        payment.tenant_id,
        "payment",
        payment.id,
        "in",
        payment.amount,
        payment.currency,
    )
    post_payment(store, payment)
    return entry


def remember_cash(store: CommerceStore, movement: CashMovement) -> LedgerEntry:
    """Upsert cash fact; voided movements keep an auditable voided ledger row."""
    from factory_os.domain.journal_posting import post_cash_movement, reverse_cash_movement

    store.add_ledger_entry(
        movement.tenant_id,
        "cash",
        movement.id,
        movement.direction,
        movement.amount,
        movement.currency,
    )
    desired = _VOIDED if (movement.status or _RECORDED) == _VOIDED else _RECORDED
    entry = store.set_ledger_entry_status(movement.tenant_id, "cash", movement.id, desired)
    if desired == _VOIDED:
        reverse_cash_movement(store, movement)
    else:
        post_cash_movement(store, movement)
    return entry


def void_cash_ledger(store: CommerceStore, movement: CashMovement) -> LedgerEntry:
    """After soft-void of cash, mark the derived ledger row voided (still present)."""
    return remember_cash(store, movement)


def remember_purchase(store: CommerceStore, receipt: PurchaseReceipt) -> LedgerEntry:
    from factory_os.domain.journal_posting import post_purchase

    amount = (receipt.unit_cost * receipt.quantity).quantize(Decimal("0.01"))
    entry = store.add_ledger_entry(
        receipt.tenant_id,
        "purchase",
        receipt.id,
        "out",
        amount,
        receipt.currency,
    )
    post_purchase(store, receipt)
    return entry


def sync_facts(store: CommerceStore, tenant_id) -> None:
    from factory_os.domain.journal_posting import sync_journal

    store.require_tenant(tenant_id)
    for payment in store.list_payments(tenant_id):
        remember_payment(store, payment)
    for movement in store.list_cash(tenant_id):
        remember_cash(store, movement)
    purchases = getattr(store, "purchases", None)
    if isinstance(purchases, list):
        for receipt in purchases:
            if getattr(receipt, "tenant_id", None) == tenant_id:
                remember_purchase(store, receipt)
    sync_journal(store, tenant_id)
