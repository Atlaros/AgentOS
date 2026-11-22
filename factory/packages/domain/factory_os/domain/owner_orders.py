"""Owner desk orders: a cash sale already collected, and edits that persist.

Customer chat never confirms a payment. This module is the human path.
It creates a pending payment with provider ``cash`` and then calls
``confirm_from_adapter`` on that reference only, so the order is placed,
the garments are marked sold, and the payment ledger runs the same way
as a Baneco confirm. Baneco is not invented. Prices and stock are read
from ``VariantRecord``.

``record_cash`` posts the drawer and the ledger inflow. Confirmed cash
payments do not also post via ``remember_payment`` (avoids a double count).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from factory_os.domain.cart_quote import charge_total, quote_lines
from factory_os.domain.models import Customer, Delivery, Order, OrderItem, Payment, PaymentStatus
from factory_os.domain.store import CommerceStore


class OwnerOrderError(Exception):
    """Validation or state conflict the panel can show as ``detail``."""

    def __init__(self, code: str, status_code: int = 400) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


@dataclass(frozen=True)
class ManualLine:
    variant_sku: str
    quantity: int


@dataclass(frozen=True)
class OwnerOrderView:
    order: Order
    payment: Payment | None
    customer: Customer
    delivery: Delivery | None


def normalize_wa(raw: str) -> str:
    """Digits only. An 8-digit Bolivian mobile gets the 591 prefix."""
    text = (raw or "").strip()
    if text.startswith("+"):
        text = text[1:]
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 8:
        digits = "591" + digits
    if len(digits) < 8 or len(digits) > 15:
        raise OwnerOrderError("bad_wa")
    return digits


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _held_by_others(store: CommerceStore, tenant_id: UUID, order_id: UUID) -> set[str]:
    """Holds that are not this order. This order may keep its own garments."""
    skus: set[str] = set()
    for order in store.list_orders(tenant_id):
        if order.id == order_id or order.status not in {"reserved", "open"}:
            continue
        if order.status == "open":
            payment = store.payment_for_order(tenant_id, order.id)
            if payment is not None and payment.status is PaymentStatus.CONFIRMED:
                continue
        for item in order.items:
            skus.add(item.variant_sku)
    for payment in store.list_payments(tenant_id):
        if (
            payment.order_id is None
            and payment.status is PaymentStatus.PENDING
            and payment.variant_sku
        ):
            skus.add(payment.variant_sku)
    return skus


def items_from_catalog(
    store: CommerceStore,
    tenant_id: UUID,
    lines: list[ManualLine],
    *,
    exclude_order_id: UUID | None = None,
) -> list[OrderItem]:
    """Build order lines at catalog price. Reject unknown, disabled, or held stock."""
    if not lines:
        raise OwnerOrderError("empty")
    merged: dict[str, int] = {}
    sequence: list[str] = []
    for line in lines:
        sku = (line.variant_sku or "").strip()
        if not sku or line.quantity < 1:
            raise OwnerOrderError("bad_quantity")
        if sku not in merged:
            sequence.append(sku)
        merged[sku] = merged.get(sku, 0) + line.quantity
    held = (
        _held_by_others(store, tenant_id, exclude_order_id)
        if exclude_order_id is not None
        else set(store.held_variant_skus(tenant_id))
    )
    items: list[OrderItem] = []
    for sku in sequence:
        quantity = merged[sku]
        record = store.get_variant(tenant_id, sku)
        if record is None:
            raise OwnerOrderError("unknown_variant")
        if record.attributes.get("disabled"):
            raise OwnerOrderError("disabled_variant", 409)
        if record.stock < quantity or sku in held:
            raise OwnerOrderError("out_of_stock", 409)
        items.append(
            OrderItem(
                variant_sku=record.variant_sku,
                name=record.name,
                quantity=quantity,
                unit_price=record.price,
                currency=record.currency,
            )
        )
    return items


def _view(store: CommerceStore, tenant_id: UUID, order: Order) -> OwnerOrderView:
    customer = store.get_customer(tenant_id, order.customer_id)
    if customer is None:
        raise OwnerOrderError("order_not_found", 404)
    return OwnerOrderView(
        order=order,
        payment=store.payment_for_order(tenant_id, order.id),
        customer=customer,
        delivery=store.delivery_for_order(tenant_id, order.id),
    )


def _fill_blank_customer(
    store: CommerceStore,
    tenant_id: UUID,
    customer: Customer,
    name: str | None,
    address: str | None,
) -> Customer:
    next_name = name if not (customer.name or "").strip() else None
    next_address = address if not (customer.address or "").strip() else None
    if next_name is None and next_address is None:
        return customer
    return store.update_customer(tenant_id, customer.wa_number, next_name, next_address)


def settle_cash(store: CommerceStore, tenant_id: UUID, order: Order, customer: Customer) -> Payment:
    """Record owner cash and confirm that cash reference. Never a Baneco ref."""
    if order.status in {"cancelled", "delivered"}:
        raise OwnerOrderError("bad_status", 409)
    existing = store.payment_for_order(tenant_id, order.id)
    if existing is not None and existing.status is PaymentStatus.CONFIRMED:
        raise OwnerOrderError("payment_locked", 409)
    if existing is not None:
        store.delete_payment(tenant_id, existing.id)
    fresh = store.get_order(tenant_id, order.id)
    if fresh is None or not fresh.items:
        raise OwnerOrderError("empty")
    # confirm_from_adapter only consumes stock when the order moves
    # reserved/open → placed. An unpaid "placed" order would skip that
    # step and leave stock untouched; normalize before confirming.
    if fresh.status == "placed":
        fresh = store.set_order_status(tenant_id, fresh.id, "reserved")
    amount = charge_total(fresh.items, fresh.discount_amount)
    if amount <= 0:
        raise OwnerOrderError("bad_amount")
    currency = fresh.items[0].currency or "BOB"
    pending = store.create_payment(
        tenant_id,
        fresh.id,
        "cash",
        f"cash-{fresh.id.hex[:12]}",
        amount,
        currency,
        "CASH",
        variant_sku=fresh.items[0].variant_sku,
        customer_id=customer.id,
    )
    store.confirm_from_adapter(pending.provider_ref)
    number = fresh.public_number or fresh.id.hex[:8]
    # T1: panel POST /api/cash requires an open session; Pedidos settle auto-opens float 0.
    from factory_os.domain.cash_drawer import ensure_open_session

    ensure_open_session(store, tenant_id, currency=currency, opened_by_name="sistema")
    store.record_cash(tenant_id, "in", amount, currency, f"pedido {number} caja")
    confirmed = store.payment_for_order(tenant_id, fresh.id)
    if confirmed is None or confirmed.provider != "cash":
        raise OwnerOrderError("payment_missing", 500)
    return confirmed


def create_manual_cash_order(
    store: CommerceStore,
    tenant_id: UUID,
    *,
    wa_number: str,
    name: str | None,
    address: str | None,
    lines: list[ManualLine],
    recipient_name: str | None = None,
    delivery_address: str | None = None,
) -> OwnerOrderView:
    wa = normalize_wa(wa_number)
    customer = store.get_or_create_customer(tenant_id, wa)
    clean_name = _clean(name)
    clean_address = _clean(address)
    if clean_name or clean_address:
        customer = store.update_customer(tenant_id, wa, clean_name, clean_address)
    built = items_from_catalog(store, tenant_id, lines)
    quote = quote_lines(built)
    order = store.create_order(
        tenant_id,
        customer.id,
        items=built,
        status="reserved",
        discount_amount=quote.discount,
    )
    settle_cash(store, tenant_id, order, customer)
    recipient = _clean(recipient_name)
    ship_to = _clean(delivery_address) or clean_address
    if recipient and ship_to:
        store.create_delivery(tenant_id, order.id, ship_to, recipient)
        customer = _fill_blank_customer(store, tenant_id, customer, recipient, ship_to)
    placed = store.get_order(tenant_id, order.id)
    if placed is None:
        raise OwnerOrderError("order_not_found", 404)
    return _view(store, tenant_id, placed)


def update_manual_order(
    store: CommerceStore,
    tenant_id: UUID,
    order_id: UUID,
    *,
    name: str | None = None,
    address: str | None = None,
    lines: list[ManualLine] | None = None,
    recipient_name: str | None = None,
    delivery_address: str | None = None,
    mark_cash_paid: bool = False,
) -> OwnerOrderView:
    order = store.get_order(tenant_id, order_id)
    if order is None:
        raise OwnerOrderError("order_not_found", 404)
    customer = store.get_customer(tenant_id, order.customer_id)
    if customer is None:
        raise OwnerOrderError("order_not_found", 404)
    payment = store.payment_for_order(tenant_id, order.id)
    confirmed = payment is not None and payment.status is PaymentStatus.CONFIRMED

    if name is not None or address is not None:
        customer = store.update_customer(
            tenant_id,
            customer.wa_number,
            _clean(name) if name is not None else None,
            _clean(address) if address is not None else None,
        )

    if lines is not None:
        if confirmed:
            raise OwnerOrderError("payment_locked", 409)
        if order.status in {"cancelled", "delivered"}:
            raise OwnerOrderError("bad_status", 409)
        built = items_from_catalog(store, tenant_id, lines, exclude_order_id=order.id)
        quote = quote_lines(built)
        order = store.replace_order_items(
            tenant_id, order.id, built, discount_amount=quote.discount
        )

    if mark_cash_paid:
        if confirmed:
            raise OwnerOrderError("payment_locked", 409)
        settle_cash(store, tenant_id, order, customer)
        refreshed = store.get_order(tenant_id, order.id)
        if refreshed is not None:
            order = refreshed

    recipient = _clean(recipient_name) if recipient_name is not None else None
    ship_to = _clean(delivery_address) if delivery_address is not None else None
    if recipient_name is not None or delivery_address is not None:
        if recipient and ship_to:
            existing = store.delivery_for_order(tenant_id, order.id)
            if existing is None:
                store.create_delivery(tenant_id, order.id, ship_to, recipient)
            else:
                store.update_delivery(tenant_id, order.id, ship_to, recipient)
            _fill_blank_customer(store, tenant_id, customer, recipient, ship_to)
        elif recipient or ship_to:
            existing = store.delivery_for_order(tenant_id, order.id)
            if existing is None:
                raise OwnerOrderError("empty")
            store.update_delivery(
                tenant_id,
                order.id,
                ship_to or existing.address,
                recipient or existing.recipient_name,
            )

    current = store.get_order(tenant_id, order.id)
    if current is None:
        raise OwnerOrderError("order_not_found", 404)
    return _view(store, tenant_id, current)
