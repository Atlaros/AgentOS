"""An open order holds its garment. Unpaid orders expire so another client can buy it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from factory_os.domain.models import ConversationStage, EmployeeRole, PaymentStatus

UNPAID_ORDER_HOLD = timedelta(minutes=15)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def release_expired_unpaid_orders(store, tenant_id: UUID, *, now: datetime | None = None) -> int:
    """Delete open orders with no confirmed payment once the hold window has passed.

    Confirmed payments stay. Cancelling or deleting the order frees the garment.
    """
    store.require_tenant(tenant_id)
    moment = _aware(now or datetime.now(UTC))
    from factory_os.domain.future_orders import apply_due_future_orders, business_today

    apply_due_future_orders(store, tenant_id, on=business_today(moment))
    released = 0
    for order in list(store.list_orders(tenant_id)):
        if getattr(order, "origin", "agent") == "counter":
            continue
        if getattr(order, "fulfill_on", None) is not None:
            continue
        if order.status == "cancelled":
            continue
        if order.status not in {"reserved", "open"} or order.created_at is None:
            continue
        window = timedelta(minutes=order.hold_minutes or UNPAID_ORDER_HOLD.seconds // 60)
        if moment - _aware(order.created_at) < window:
            continue
        payment = store.payment_for_order(tenant_id, order.id)
        if payment is not None and payment.status is PaymentStatus.CONFIRMED:
            continue
        _forget_order(store, tenant_id, order.id)
        store.delete_order(tenant_id, order.id)
        released += 1
    for payment in list(store.list_payments(tenant_id)):
        if payment.order_id is not None or payment.status is PaymentStatus.CONFIRMED:
            continue
        if payment.created_at is None:
            continue
        if moment - _aware(payment.created_at) < UNPAID_ORDER_HOLD:
            continue
        # Walk-in QR payments are linked from cash_sale_tickets.payment_id.
        # Deleting them raises ForeignKeyViolation on Postgres and 500s catalog search.
        ticket = None
        if payment.id is not None and hasattr(store, "cash_sale_ticket_for_payment"):
            ticket = store.cash_sale_ticket_for_payment(tenant_id, payment.id)
        if ticket is not None:
            if ticket.status == "pending_qr":
                store.set_cash_sale_status(tenant_id, ticket.id, "voided")
                if hasattr(store, "set_payment_status"):
                    store.set_payment_status(
                        tenant_id, payment.id, PaymentStatus.EXPIRED.value
                    )
                else:
                    payment.status = PaymentStatus.EXPIRED
                _forget_checkout(store, tenant_id, payment.provider_ref)
                released += 1
            continue
        _forget_checkout(store, tenant_id, payment.provider_ref)
        store.delete_payment(tenant_id, payment.id)
        released += 1
    return released


def _forget_order(store, tenant_id: UUID, order_id: UUID) -> None:
    for conv in store.list_conversations(tenant_id):
        state = conv.state
        if state.order_id != order_id and state.folder.order_id != order_id:
            continue
        state.order_id = None
        state.payment_id = None
        state.provider_ref = None
        state.graph_node = None
        if state.stage is ConversationStage.CHECKOUT:
            state.stage = ConversationStage.DISCOVERY
        state.pass_to(
            EmployeeRole.SALES,
            from_role=EmployeeRole.COBROS,
            reason="order_expired",
            payment_state="none",
        )
        store.save_conversation_state(conv)


def _forget_checkout(store, tenant_id: UUID, provider_ref: str) -> None:
    for conv in store.list_conversations(tenant_id):
        state = conv.state
        if state.provider_ref != provider_ref:
            continue
        state.payment_id = None
        state.provider_ref = None
        state.graph_node = None
        if state.stage is ConversationStage.CHECKOUT:
            state.stage = ConversationStage.DISCOVERY
        state.pass_to(
            EmployeeRole.SALES,
            from_role=EmployeeRole.COBROS,
            reason="checkout_expired",
            payment_state="none",
        )
        store.save_conversation_state(conv)
