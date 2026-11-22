"""Human close of a paused WhatsApp chat.

The four buttons record a fact. Free text never confirms a payment.
"""

from __future__ import annotations

from factory_os.domain.models import Conversation, ConversationStage, EmployeeRole, PaymentStatus
from factory_os.domain.store import CommerceStore

ACTIONS = frozenset({"wait_qr", "paid_cash", "no_sale", "continue"})


class ChatCloseError(Exception):
    """State conflict the panel shows as ``detail``."""

    def __init__(self, code: str, status_code: int = 409) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


def apply_chat_close(store: CommerceStore, conversation: Conversation, action: str) -> str:
    """Apply one close action. Returns the action code. Mutates the conversation."""
    if action not in ACTIONS:
        raise ChatCloseError("bad_action", 400)
    if action == "wait_qr":
        return _wait_qr(store, conversation)
    if action == "paid_cash":
        return _paid_cash(store, conversation)
    if action == "no_sale":
        return _no_sale(store, conversation)
    return _continue(store, conversation)


def chat_has_products(store: CommerceStore, conversation: Conversation) -> bool:
    order = _order(store, conversation)
    if order is not None and order.items:
        return True
    return bool(conversation.state.cart)


def chat_has_qr(store: CommerceStore, conversation: Conversation) -> bool:
    payment = _payment(store, conversation)
    return payment is not None and payment.status is not PaymentStatus.CONFIRMED


def _wait_qr(store: CommerceStore, conversation: Conversation) -> str:
    if not chat_has_products(store, conversation):
        raise ChatCloseError("no_products")
    if not chat_has_qr(store, conversation):
        raise ChatCloseError("no_qr")
    state = conversation.state
    state.chat_resolution = "wait_qr"
    state.human_takeover = False
    state.needs_human = False
    state.discovery_asked = True
    state.graph_node = "cobros"
    state.pass_to(
        EmployeeRole.COBROS,
        from_role=EmployeeRole.COBROS,
        pending="wait_adapter",
        reason="qr_awaiting_bank",
        payment_state="pending",
    )
    return "wait_qr"


def _paid_cash(store: CommerceStore, conversation: Conversation) -> str:
    from factory_os.domain.owner_orders import OwnerOrderError, settle_cash

    order = _order(store, conversation)
    if order is None or not order.items:
        raise ChatCloseError("no_products")
    customer = store.get_customer(conversation.tenant_id, conversation.customer_id)
    if customer is None:
        raise ChatCloseError("no_customer", 404)
    try:
        payment = settle_cash(store, conversation.tenant_id, order, customer)
    except OwnerOrderError as exc:
        raise ChatCloseError(exc.code, exc.status_code) from exc
    state = conversation.state
    state.payment_id = payment.id
    state.provider_ref = payment.provider_ref
    state.chat_resolution = "paid_cash"
    state.human_takeover = False
    state.needs_human = False
    state.stage = ConversationStage.PURCHASED
    state.graph_node = "operaciones"
    state.pass_to(
        EmployeeRole.OPS,
        from_role=EmployeeRole.COBROS,
        pending="collect_address",
        reason="paid_cash",
        payment_state="confirmed",
    )
    return "paid_cash"


def _no_sale(store: CommerceStore, conversation: Conversation) -> str:
    from factory_os.domain.learning import mark_conversation_outcome

    order = _order(store, conversation)
    if order is not None:
        payment = store.payment_for_order(conversation.tenant_id, order.id)
        if payment is not None and payment.status is PaymentStatus.CONFIRMED:
            raise ChatCloseError("payment_locked")
        if order.status in {"placed", "delivered"}:
            raise ChatCloseError("payment_locked")
        store.delete_order(conversation.tenant_id, order.id)
    state = conversation.state
    state.order_id = None
    state.payment_id = None
    state.provider_ref = None
    state.cart = []
    state.chat_resolution = "no_sale"
    state.human_takeover = False
    state.needs_human = False
    state.graph_node = None
    state.pass_to(None, reason="no_sale", payment_state="none")
    mark_conversation_outcome(conversation, "abandoned", reason="no_sale")
    return "no_sale"


def _continue(store: CommerceStore, conversation: Conversation) -> str:
    state = conversation.state
    state.chat_resolution = "continue"
    state.human_takeover = False
    state.needs_human = False
    state.discovery_asked = True
    if not (state.customer_need or "").strip():
        state.customer_need = _sale_need(store, conversation)
    state.graph_node = "adri"
    state.pass_to(
        EmployeeRole.SALES,
        from_role=EmployeeRole.SALES,
        reason="continue_sale",
        payment_state="pending" if chat_has_qr(store, conversation) else "none",
    )
    return "continue"


def _order(store: CommerceStore, conversation: Conversation):
    order_id = conversation.state.order_id
    if order_id is None:
        return None
    return store.get_order(conversation.tenant_id, order_id)


def _payment(store: CommerceStore, conversation: Conversation):
    payment_id = conversation.state.payment_id
    if payment_id is None:
        return None
    return store.get_payment(conversation.tenant_id, payment_id)


def _sale_need(store: CommerceStore, conversation: Conversation) -> str:
    for line in conversation.state.cart:
        name = str(line.get("name") or "").strip()
        if name:
            return name
    order = _order(store, conversation)
    if order is not None and order.items:
        return order.items[0].name or order.items[0].variant_sku
    return "la venta en curso"
