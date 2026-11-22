"""T8: the human closes a paused chat without the prose confirming a payment."""

from uuid import UUID

from factory_os.contracts.employees import identity_for
from factory_os.domain.models import EmployeeRole, PILOT_TENANT_ID, PaymentStatus
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"


def _reserved_chat(shop):
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170001111")
    conversation = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    cobros = identity_for(EmployeeRole.COBROS, PILOT_TENANT_ID)
    created = shop.tools.execute(
        cobros,
        "payment.create_qr",
        {"variant_sku": SKU, "quantity": 1, "customer_id": str(customer.id)},
        channel="whatsapp",
    )
    conversation.state.order_id = UUID(created["order_id"])
    conversation.state.payment_id = UUID(created["payment_id"])
    conversation.state.provider_ref = created["provider_ref"]
    conversation.state.cart = [
        {
            "variant_sku": SKU,
            "quantity": 1,
            "name": "Hoodie",
            "unit_price": "1",
            "currency": "BOB",
        }
    ]
    shop.store.save_conversation_state(conversation)
    shop.set_takeover(PILOT_TENANT_ID, conversation.id, True)
    return conversation


def test_human_prose_does_not_confirm_payment() -> None:
    shop = make_shop()
    conversation = _reserved_chat(shop)
    client = owner_client(shop)
    reply = client.post(
        f"/api/conversations/{conversation.id}/reply",
        json={"text": "ya pagué en efectivo"},
    )
    assert reply.status_code == 200
    payment = shop.store.get_payment(PILOT_TENANT_ID, conversation.state.payment_id)
    assert payment is not None
    assert payment.status is not PaymentStatus.CONFIRMED
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == 1


def test_leave_qr_keeps_the_order_and_the_agent_does_not_rebuild() -> None:
    shop = make_shop()
    conversation = _reserved_chat(shop)
    client = owner_client(shop)
    closed = client.post(
        f"/api/conversations/{conversation.id}/close",
        json={"action": "wait_qr"},
    )
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["action"] == "wait_qr"
    assert body["has_products"] is True
    order = shop.store.get_order(PILOT_TENANT_ID, conversation.state.order_id)
    assert order is not None
    assert order.status == "reserved"
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == 1
    saved = shop.store.get_conversation(PILOT_TENANT_ID, conversation.id)
    assert saved is not None
    assert saved.state.human_takeover is False
    assert saved.state.chat_resolution == "wait_qr"
    before = shop.store.list_orders(PILOT_TENANT_ID)
    shop.handle_turn(PILOT_TENANT_ID, "59170001111", "ya pagué")
    assert len(shop.store.list_orders(PILOT_TENANT_ID)) == len(before)
    payment = shop.store.get_payment(PILOT_TENANT_ID, conversation.state.payment_id)
    assert payment is not None
    assert payment.status is not PaymentStatus.CONFIRMED


def test_leave_qr_is_off_without_products() -> None:
    shop = make_shop()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170002222")
    conversation = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    client = owner_client(shop)
    closed = client.post(
        f"/api/conversations/{conversation.id}/close",
        json={"action": "wait_qr"},
    )
    assert closed.status_code == 409
    assert closed.json()["detail"] == "no_products"


def test_cash_close_confirms_once_and_decrements_stock() -> None:
    shop = make_shop()
    conversation = _reserved_chat(shop)
    client = owner_client(shop)
    closed = client.post(
        f"/api/conversations/{conversation.id}/close",
        json={"action": "paid_cash"},
    )
    assert closed.status_code == 200, closed.text
    order = shop.store.get_order(PILOT_TENANT_ID, conversation.state.order_id)
    assert order is not None
    assert order.status == "placed"
    payment = shop.store.get_payment(PILOT_TENANT_ID, UUID(closed.json()["payment_id"]))
    assert payment is not None
    assert payment.status is PaymentStatus.CONFIRMED
    assert payment.provider == "cash"
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == 0
    again = client.post(
        f"/api/conversations/{conversation.id}/close",
        json={"action": "paid_cash"},
    )
    assert again.status_code == 409
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == 0


def test_no_sale_releases_the_hold_and_closes_the_chat() -> None:
    shop = make_shop()
    conversation = _reserved_chat(shop)
    client = owner_client(shop)
    closed = client.post(
        f"/api/conversations/{conversation.id}/close",
        json={"action": "no_sale"},
    )
    assert closed.status_code == 200, closed.text
    assert shop.store.get_order(PILOT_TENANT_ID, conversation.state.order_id) is None
    assert SKU not in shop.store.held_variant_skus(PILOT_TENANT_ID)
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == 1
    saved = shop.store.get_conversation(PILOT_TENANT_ID, conversation.id)
    assert saved is not None
    assert saved.outcome == "abandoned"
    assert saved.closed_at is not None
    assert saved.state.order_id is None
    assert saved.state.human_takeover is False


def test_continue_sale_does_not_charge_or_close() -> None:
    shop = make_shop()
    conversation = _reserved_chat(shop)
    client = owner_client(shop)
    closed = client.post(
        f"/api/conversations/{conversation.id}/close",
        json={"action": "continue"},
    )
    assert closed.status_code == 200, closed.text
    saved = shop.store.get_conversation(PILOT_TENANT_ID, conversation.id)
    assert saved is not None
    assert saved.state.chat_resolution == "continue"
    assert saved.state.human_takeover is False
    assert saved.state.order_id == conversation.state.order_id
    assert saved.outcome is None
    assert saved.closed_at is None
    payment = shop.store.get_payment(PILOT_TENANT_ID, conversation.state.payment_id)
    assert payment is not None
    assert payment.status is not PaymentStatus.CONFIRMED
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == 1
