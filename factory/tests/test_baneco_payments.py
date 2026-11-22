"""Baneco / fake payment adapter — webhook confirms, chat does not."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from factory_os.agents.turn import ShopRuntime
from factory_os.domain.models import OrderItem, PILOT_TENANT_ID, PaymentStatus
from factory_os.tools.payments import BanecoPaymentProvider, FakePaymentProvider, build_payment_provider
from tests.conftest import OWNER_TOKEN, api_settings, make_shop, owner_client


def test_fake_create_qr_has_expires() -> None:
    payments = FakePaymentProvider()
    issued = payments.create_qr(str(uuid4()), Decimal("1.00"), "BOB")
    assert issued.provider_ref.startswith("pay-")
    assert issued.expires_at is not None
    assert payments.status(issued.provider_ref) is PaymentStatus.PENDING


def test_fake_webhook_confirms_with_signature() -> None:
    shop = make_shop()
    payments = FakePaymentProvider()
    shop.payments = payments
    shop._bind_tools()
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        shop.store.get_or_create_customer(PILOT_TENANT_ID, "59193000001").id,
        OrderItem("pago1-U-B", "Blusa prueba pago 1", 1, Decimal("1.00"), "BOB"),
    )
    issued = payments.create_qr(str(order.id), Decimal("1.00"), "BOB")
    shop.store.create_payment(
        PILOT_TENANT_ID, order.id, "fake", issued.provider_ref, Decimal("1.00"), "BOB", issued.qr_payload
    )
    body = json.dumps(
        {"event_id": "evt-1", "provider_reference": issued.provider_ref, "state": "confirmed"}
    ).encode()
    sig = hmac.new(payments.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    before = shop.store.get_variant(PILOT_TENANT_ID, "pago1-U-B")
    assert before is not None
    assert not before.attributes.get("disabled")
    assert before.stock >= 1
    opening_stock = before.stock
    result = shop.apply_payment_webhook(body, {"X-Fake-Signature": sig})
    assert result["status"] == "ok"
    assert shop.store.payment_status(PILOT_TENANT_ID, issued.provider_ref).status is PaymentStatus.CONFIRMED
    sold = shop.store.get_variant(PILOT_TENANT_ID, "pago1-U-B")
    assert sold is not None
    assert sold.stock == opening_stock - 1
    assert not sold.attributes.get("disabled")
    other = shop.store.get_variant(PILOT_TENANT_ID, "pago2-U-N")
    assert other is not None
    assert not other.attributes.get("disabled")
    assert other.stock >= 1
    dup = shop.apply_payment_webhook(body, {"X-Fake-Signature": sig})
    assert dup["status"] == "duplicate"


def test_confirmed_chat_payment_decrements_quantity() -> None:
    shop = make_shop()
    payments = FakePaymentProvider()
    shop.payments = payments
    shop._bind_tools()
    sku = "pago1-U-B"
    shop.store.set_variant_availability(PILOT_TENANT_ID, sku, available=True, stock=4)
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59193000099")
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem(sku, "Blusa prueba pago 1", 2, Decimal("1.00"), "BOB"),
    )
    issued = payments.create_qr(str(order.id), Decimal("2.00"), "BOB")
    shop.store.create_payment(
        PILOT_TENANT_ID,
        order.id,
        "fake",
        issued.provider_ref,
        Decimal("2.00"),
        "BOB",
        issued.qr_payload,
    )
    body = json.dumps(
        {"event_id": "evt-qty", "provider_reference": issued.provider_ref, "state": "confirmed"}
    ).encode()
    sig = hmac.new(payments.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    result = shop.apply_payment_webhook(body, {"X-Fake-Signature": sig})
    assert result["status"] == "ok"
    sold = shop.store.get_variant(PILOT_TENANT_ID, sku)
    assert sold is not None
    assert sold.stock == 2
    assert not sold.attributes.get("disabled")


def _crash_once_on_confirm(shop: ShopRuntime) -> None:
    real_confirm = shop.store.confirm_from_adapter
    calls = {"n": 0}

    def flaky(provider_ref: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("crash after the event was recorded")
        real_confirm(provider_ref)

    shop.store.confirm_from_adapter = flaky  # type: ignore[method-assign]


def _signed_fake_event(payments: FakePaymentProvider, event_id: str, provider_ref: str) -> tuple[bytes, dict[str, str]]:
    body = json.dumps({"event_id": event_id, "provider_reference": provider_ref, "state": "confirmed"}).encode()
    sig = hmac.new(payments.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Fake-Signature": sig}


def test_replay_after_crash_promotes_reservation_once() -> None:
    shop = make_shop()
    payments = FakePaymentProvider()
    shop.payments = payments
    shop._bind_tools()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59193000021")
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("pago1-U-B", "Blusa prueba pago 1", 1, Decimal("1.00"), "BOB"),
        status="reserved",
    )
    issued = payments.create_qr(str(order.id), Decimal("1.00"), "BOB")
    shop.store.create_payment(
        PILOT_TENANT_ID, order.id, "fake", issued.provider_ref, Decimal("1.00"), "BOB", issued.qr_payload
    )
    body, headers = _signed_fake_event(payments, "evt-crash-1", issued.provider_ref)
    opening = shop.store.get_variant(PILOT_TENANT_ID, "pago1-U-B")
    assert opening is not None
    opening_stock = opening.stock
    _crash_once_on_confirm(shop)

    try:
        shop.apply_payment_webhook(body, headers)
    except RuntimeError:
        pass
    assert shop.store.get_order(PILOT_TENANT_ID, order.id).status == "reserved"

    replay = shop.apply_payment_webhook(body, headers)
    assert replay["status"] == "duplicate"
    assert shop.store.get_order(PILOT_TENANT_ID, order.id).status == "placed"
    assert shop.store.payment_status(PILOT_TENANT_ID, issued.provider_ref).status is PaymentStatus.CONFIRMED
    sold = shop.store.get_variant(PILOT_TENANT_ID, "pago1-U-B")
    assert sold is not None and sold.stock == opening_stock - 1 and not sold.attributes.get("disabled")

    again = shop.apply_payment_webhook(body, headers)
    assert again["status"] == "duplicate"
    assert [o.id for o in shop.store.list_orders(PILOT_TENANT_ID)] == [order.id]
    assert shop.store.get_order(PILOT_TENANT_ID, order.id).status == "placed"


def test_replay_after_crash_creates_single_order_for_qr_without_order() -> None:
    shop = make_shop()
    payments = FakePaymentProvider()
    shop.payments = payments
    shop._bind_tools()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59193000022")
    issued = payments.create_qr(str(uuid4()), Decimal("1.00"), "BOB")
    shop.store.create_payment(
        PILOT_TENANT_ID,
        None,
        "fake",
        issued.provider_ref,
        Decimal("1.00"),
        "BOB",
        issued.qr_payload,
        variant_sku="pago2-U-N",
        customer_id=customer.id,
    )
    body, headers = _signed_fake_event(payments, "evt-crash-2", issued.provider_ref)
    _crash_once_on_confirm(shop)

    try:
        shop.apply_payment_webhook(body, headers)
    except RuntimeError:
        pass
    assert shop.store.list_orders(PILOT_TENANT_ID) == []

    shop.apply_payment_webhook(body, headers)
    shop.apply_payment_webhook(body, headers)
    orders = shop.store.list_orders(PILOT_TENANT_ID)
    assert len(orders) == 1
    assert orders[0].status == "placed"
    assert orders[0].items[0].variant_sku == "pago2-U-N"


def test_qr_without_order_creates_order_when_bank_confirms() -> None:
    shop = make_shop()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59193000009")
    payments = FakePaymentProvider()
    issued = payments.create_qr(str(uuid4()), Decimal("1.00"), "BOB")
    shop.store.create_payment(
        PILOT_TENANT_ID,
        None,
        "fake",
        issued.provider_ref,
        Decimal("1.00"),
        "BOB",
        issued.qr_payload,
        variant_sku="pago2-U-N",
        customer_id=customer.id,
    )
    assert shop.store.list_orders(PILOT_TENANT_ID) == []
    before = shop.store.get_variant(PILOT_TENANT_ID, "pago2-U-N")
    assert before is not None
    opening_stock = before.stock
    shop.payments = payments
    shop.confirm_payment_from_adapter(issued.provider_ref)
    orders = shop.store.list_orders(PILOT_TENANT_ID)
    assert len(orders) == 1
    assert orders[0].status == "placed"
    assert orders[0].items[0].variant_sku == "pago2-U-N"
    sold = shop.store.get_variant(PILOT_TENANT_ID, "pago2-U-N")
    assert sold is not None
    assert sold.stock == opening_stock - 1
    assert not sold.attributes.get("disabled")
    still = shop.store.get_variant(PILOT_TENANT_ID, "pago1-U-B")
    assert still is not None
    assert not still.attributes.get("disabled")


def test_baneco_create_qr_and_notify_fixture() -> None:
    provider = BanecoPaymentProvider(
        base_url="https://baneco.test",
        username="u",
        password="p",
        aes_key="k",
        account_credit="123",
        generate_fn=lambda txn, amount, currency: {
            "qrId": "bn-qr-1",
            "qrImage": "iVBORw0KGgo=",
        },
        status_fn=lambda qr_id: {"responseCode": 0, "statusQRCode": 1, "payment": []},
    )
    issued = provider.create_qr(str(uuid4()), Decimal("1"), "BOB")
    assert issued.provider_ref == "bn-qr-1"
    assert issued.qr_payload.startswith("iVBOR")
    assert provider.status("bn-qr-1") is PaymentStatus.CONFIRMED

    body = json.dumps(
        {"Payment": {"qrId": "bn-qr-1", "transactionId": "ac1", "amount": 1.0, "currency": "BOB"}}
    ).encode()
    event = provider.parse_webhook(body, {})
    assert event.state is PaymentStatus.CONFIRMED
    assert event.event_id == "baneco-notify:bn-qr-1:ac1"
    assert event.provider_reference == "bn-qr-1"


def test_baneco_notify_requires_secret_when_configured() -> None:
    provider = BanecoPaymentProvider(
        base_url="https://baneco.test",
        username="u",
        password="p",
        aes_key="k",
        account_credit="123",
        notify_shared_secret="s3cret",
        generate_fn=lambda *_a: {"qrId": "q", "qrImage": "x"},
        status_fn=lambda *_a: {"responseCode": 0, "statusQRCode": 1},
    )
    body = json.dumps({"Payment": {"qrId": "q", "transactionId": "t"}}).encode()
    try:
        provider.parse_webhook(body, {})
        raise AssertionError("expected unauthorized")
    except ValueError as exc:
        assert "unauthorized" in str(exc)
    event = provider.parse_webhook(body, {"X-Baneco-Notify-Secret": "s3cret"})
    assert event.state is PaymentStatus.CONFIRMED


def test_build_payment_provider_defaults_fake(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_LIVE_PAYMENTS", raising=False)
    monkeypatch.setenv("QR_PROVIDER", "baneco")
    assert build_payment_provider().name == "fake"


def test_build_payment_provider_live_qr_provider_alias(monkeypatch) -> None:
    monkeypatch.delenv("QR_PROVIDER", raising=False)
    monkeypatch.delenv("BANK_TX_PROVIDER", raising=False)
    monkeypatch.setenv("ENABLE_LIVE_PAYMENTS", "true")
    monkeypatch.setenv("LIVE_QR_PROVIDER", "baneco")
    monkeypatch.setenv("BANECO_API_BASE_URL", "https://apimkt.example/")
    monkeypatch.setenv("BANECO_USERNAME", "user")
    monkeypatch.setenv("BANECO_PASSWORD", "pass")
    monkeypatch.setenv("BANECO_AES_KEY", "key32charskey32charskey32chars12")
    monkeypatch.setenv("BANECO_ACCOUNT_CREDIT", "1234567890")
    assert build_payment_provider().name == "baneco"


def test_build_payment_provider_baneco_when_live(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_PAYMENTS", "true")
    monkeypatch.setenv("QR_PROVIDER", "baneco")
    monkeypatch.setenv("BANECO_API_BASE_URL", "https://apimkt.example/")
    monkeypatch.setenv("BANECO_USERNAME", "user")
    monkeypatch.setenv("BANECO_PASSWORD", "pass")
    monkeypatch.setenv("BANECO_AES_KEY", "key32charskey32charskey32chars12")
    monkeypatch.setenv("BANECO_ACCOUNT_CREDIT", "1234567890")
    assert build_payment_provider().name == "baneco"


def test_ya_pague_does_not_confirm_via_chat() -> None:
    shop = make_shop()
    wa = "59193000002"
    shop.handle_turn(PILOT_TENANT_ID, wa, "quiero la blusa p001")
    shop.handle_turn(PILOT_TENANT_ID, wa, "confirmo")
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, wa)
    conv = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    if conv.state.order_id is None:
        return
    shop.handle_turn(PILOT_TENANT_ID, wa, "ya pagué")
    payment = shop.store.payment_for_order(PILOT_TENANT_ID, conv.state.order_id)
    if payment is not None:
        assert payment.status is not PaymentStatus.CONFIRMED


def test_fake_confirm_endpoint_rejects_non_fake() -> None:
    from factory_os.api.main import create_app

    shop = make_shop()
    shop.payments = BanecoPaymentProvider(
        base_url="https://baneco.test",
        username="u",
        password="p",
        aes_key="k",
        account_credit="1",
        generate_fn=lambda *_a: {"qrId": "x", "qrImage": "q"},
    )
    shop._bind_tools()
    client = owner_client(shop)
    response = client.post("/payments/fake-confirm", params={"provider_ref": "x"})
    assert response.status_code == 400


def test_fake_payment_routes_are_hidden_outside_test() -> None:
    from factory_os.api.main import create_app

    for app_env in ("local", "production", ""):
        client = TestClient(create_app(make_shop(), api_settings(app_env=app_env)))
        headers = {"Authorization": f"Bearer {OWNER_TOKEN}"}
        confirm = client.post("/payments/fake-confirm", params={"provider_ref": "x"}, headers=headers)
        webhook = client.post("/webhooks/payments/fake", content=b"{}", headers=headers)
        assert confirm.status_code == 404, app_env
        assert webhook.status_code == 404, app_env


def test_fake_confirm_requires_owner_token_in_test() -> None:
    from factory_os.api.main import create_app

    client = TestClient(create_app(make_shop(), api_settings()))
    assert client.post("/payments/fake-confirm", params={"provider_ref": "x"}).status_code == 401
