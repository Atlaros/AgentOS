"""Invoice port. The document has its own status and never writes payments."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from factory_os.domain.models import InvoiceDocument, InvoiceStatus
from factory_os.domain.store import CommerceStore

INVOICE_STATUSES = {item.value for item in InvoiceStatus}


class InvoicePort(Protocol):
    def submit(self, document_id: str, amount: Decimal, currency: str) -> "InvoiceSubmission": ...


@dataclass(frozen=True)
class InvoiceSubmission:
    status: str
    external_ref: str


class FakeInvoicePort:
    """Records the attempt. Used in tests and until a real ERP is plugged in."""

    name = "fake"

    def __init__(self) -> None:
        self.attempts: list[str] = []

    def submit(self, document_id: str, amount: Decimal, currency: str) -> InvoiceSubmission:
        _ = amount, currency
        self.attempts.append(document_id)
        return InvoiceSubmission(status=InvoiceStatus.ISSUED.value, external_ref=f"fake-{document_id[:8]}")


def issue_invoice(
    store: CommerceStore,
    port: InvoicePort,
    tenant_id: UUID,
    order_id: UUID,
) -> InvoiceDocument:
    from factory_os.domain.cart_quote import charge_total

    order = store.get_order(tenant_id, order_id)
    if order is None:
        raise KeyError(order_id)
    currency = order.items[0].currency if order.items else "BOB"
    amount = charge_total(order.items, order.discount_amount)
    document = store.add_invoice_document(tenant_id, order_id, amount, currency)
    try:
        submission = port.submit(str(document.id), amount, currency)
    except Exception:
        return store.set_invoice_status(tenant_id, document.id, InvoiceStatus.FAILED.value, "")
    status = submission.status if submission.status in INVOICE_STATUSES else InvoiceStatus.FAILED.value
    return store.set_invoice_status(tenant_id, document.id, status, submission.external_ref)
