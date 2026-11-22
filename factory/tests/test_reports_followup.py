"""Slice B: readable follow-up rows and analytics deep links."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from factory_os.domain.analytics import build_analytics_summary
from factory_os.domain.analytics_thresholds import AnalyticsThresholds
from factory_os.domain.models import Conversation, OrderItem, PILOT_TENANT_ID, PaymentStatus
from factory_os.domain.reports import alert_payload
from tests.conftest import api_settings, make_shop, owner_client

NOW = datetime(2026, 11, 11, 15, tzinfo=UTC)
FOLLOWUP_HREF = "/reports?tab=seguimiento"


def _client(shop) -> TestClient:
    from factory_os.api.main import create_app

    return TestClient(create_app(shop, api_settings()))


def _expired_payment(shop, *, wa_number: str, name: str | None, public_number: str | None, amount: str):
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, wa_number)
    customer.name = name
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("h001-M-VP", "blusa", 1, Decimal(amount), "BOB"),
    )
    order.public_number = public_number
    payment = shop.store.create_payment(
        PILOT_TENANT_ID,
        order.id,
        "fake",
        f"pay-{wa_number}",
        Decimal(amount),
        "BOB",
        "QR:expired",
        customer_id=customer.id,
    )
    payment.status = PaymentStatus.EXPIRED
    payment.created_at = NOW - timedelta(days=6, hours=3)
    return customer, order, payment


def _quiet_customer(shop, wa_number: str, name: str | None, *, days_ago: int):
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, wa_number)
    customer.name = name
    latest = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    shop.store.append_message(latest, "customer", "último")
    latest.last_message_at = NOW - timedelta(days=days_ago, hours=2)
    older = Conversation(
        id=uuid4(),
        tenant_id=PILOT_TENANT_ID,
        customer_id=customer.id,
        last_message_at=NOW - timedelta(days=days_ago + 9),
    )
    shop.store.conversations[older.id] = older
    return customer, latest


def test_overdue_payment_row_names_the_order_customer_and_days() -> None:
    shop = make_shop()
    customer, order, payment = _expired_payment(
        shop,
        wa_number="59170005111",
        name="Lucía Mora",
        public_number="AC-FOLLOW1",
        amount="145.00",
    )
    blank, blank_order, blank_payment = _expired_payment(
        shop,
        wa_number="59170005112",
        name="   ",
        public_number=None,
        amount="80.00",
    )

    payload = alert_payload(shop.store, PILOT_TENANT_ID, NOW)
    rows = {row["id"]: row for row in payload["overdue_payments"]}

    named = rows[str(payment.id)]
    assert named["provider_ref"] == payment.provider_ref
    assert named["amount"] == "145.00"
    assert named["currency"] == "BOB"
    assert named["status"] == "expired"
    assert named["status_label"] == "Vencido"
    assert named["order_id"] == str(order.id)
    assert named["order_label"] == "AC-FOLLOW1"
    assert named["customer_id"] == str(customer.id)
    assert named["customer_label"] == "Lucía Mora"
    assert named["overdue_days"] == 6
    assert named["href_open"] == "/orders?q=AC-FOLLOW1"
    assert "gestionado" not in named

    unnamed = rows[str(blank_payment.id)]
    assert unnamed["order_id"] == str(blank_order.id)
    assert unnamed["order_label"] == f"Pedido {str(blank_order.id)[:8]}"
    assert unnamed["customer_id"] == str(blank.id)
    assert unnamed["customer_label"] == "59170005112"
    assert unnamed["customer_label"] != "Sin nombre"
    assert unnamed["href_open"] == f"/orders?q={blank_order.id}"
    assert unnamed["status_label"] == "Vencido"
    assert unnamed["overdue_days"] == 6


def test_overdue_without_order_uses_provider_ref_and_sin_cliente() -> None:
    shop = make_shop()
    payment = shop.store.create_payment(
        PILOT_TENANT_ID,
        None,
        "fake",
        "qr-orphan-12",
        Decimal("12.00"),
        "BOB",
        "QR:orphan",
    )
    payment.status = PaymentStatus.EXPIRED
    payment.created_at = NOW - timedelta(hours=2)

    payload = alert_payload(shop.store, PILOT_TENANT_ID, NOW)
    row = next(r for r in payload["overdue_payments"] if r["id"] == str(payment.id))
    assert row["order_label"] == "qr-orphan-12"
    assert row["customer_label"] == "Sin cliente"
    assert row["customer_id"] == ""
    assert row["order_id"] is None


def test_inactive_customer_row_uses_phone_and_spanish_relative_time() -> None:
    shop = make_shop()
    shop.store.put_analytics_thresholds(
        PILOT_TENANT_ID,
        AnalyticsThresholds(inactive_days=1),
    )
    named, named_chat = _quiet_customer(shop, "59170005221", "Ana", days_ago=12)
    phone_only, phone_chat = _quiet_customer(shop, "59170005222", None, days_ago=1)
    phone_only.name = None

    payload = alert_payload(shop.store, PILOT_TENANT_ID, NOW)
    assert payload["inactive_days"] == 1
    rows = {row["id"]: row for row in payload["inactive_customers"]}

    ana = rows[str(named.id)]
    assert ana["name"] == "Ana"
    assert ana["wa_number"] == "59170005221"
    assert ana["display_name"] == "Ana"
    assert ana["last_message_at"] == named_chat.last_message_at.isoformat()
    assert ana["last_message_relative"] == "hace 12 días"
    assert ana["inactive_days"] == 1
    assert ana["conversation_id"] == str(named_chat.id)
    assert ana["href_open"] == f"/chats/{named_chat.id}"

    quiet = rows[str(phone_only.id)]
    assert quiet["display_name"] == "59170005222"
    assert quiet["display_name"] != "Sin nombre"
    assert quiet["name"] in ("", None)
    assert quiet["last_message_relative"] == "hace 1 día"
    assert quiet["conversation_id"] == str(phone_chat.id)
    assert quiet["href_open"] == f"/chats/{phone_chat.id}"
    assert quiet["inactive_days"] == 1


def test_inactive_list_follows_the_analytics_threshold() -> None:
    shop = make_shop()
    customer, _chat = _quiet_customer(shop, "59170005331", "Beto", days_ago=20)

    before = alert_payload(shop.store, PILOT_TENANT_ID, NOW)
    assert before["inactive_days"] == 30
    assert str(customer.id) not in {row["id"] for row in before["inactive_customers"]}

    shop.store.put_analytics_thresholds(
        PILOT_TENANT_ID,
        AnalyticsThresholds(inactive_days=10),
    )
    after = alert_payload(shop.store, PILOT_TENANT_ID, NOW)
    assert after["inactive_days"] == 10
    match = next(row for row in after["inactive_customers"] if row["id"] == str(customer.id))
    assert match["inactive_days"] == 10
    assert match["display_name"] == "Beto"


def test_alerts_endpoint_returns_followup_fields_without_confirming() -> None:
    shop = make_shop()
    customer, order, payment = _expired_payment(
        shop,
        wa_number="59170005441",
        name="Nora",
        public_number="AC-API1",
        amount="145.00",
    )
    quiet, chat = _quiet_customer(shop, "59170005442", None, days_ago=40)

    anonymous = _client(shop)
    assert anonymous.get("/api/alerts").status_code == 401

    client = owner_client(shop)
    response = client.get("/api/alerts")
    assert response.status_code == 200
    body = response.json()
    overdue = next(row for row in body["overdue_payments"] if row["provider_ref"] == payment.provider_ref)
    assert overdue["status"] == "expired"
    assert overdue["status_label"] == "Vencido"
    assert overdue["order_label"] == "AC-API1"
    assert overdue["customer_label"] == "Nora"
    assert overdue["order_id"] == str(order.id)
    assert overdue["customer_id"] == str(customer.id)
    assert isinstance(overdue["overdue_days"], int)
    assert overdue["overdue_days"] >= 0
    assert overdue["href_open"].startswith("/orders?q=")
    assert overdue["amount"] == "145.00"
    assert overdue["currency"] == "BOB"

    inactive = next(row for row in body["inactive_customers"] if row["id"] == str(quiet.id))
    assert inactive["display_name"] == quiet.wa_number
    assert inactive["display_name"] != "Sin nombre"
    assert inactive["wa_number"] == quiet.wa_number
    assert inactive["last_message_relative"].startswith("hace ")
    assert inactive["conversation_id"] == str(chat.id)
    assert inactive["href_open"] == f"/chats/{chat.id}"
    assert body["inactive_days"] == inactive["inactive_days"] == 30
    assert shop.store.get_payment(PILOT_TENANT_ID, payment.id).status is PaymentStatus.EXPIRED


def test_analytics_followup_alerts_link_to_seguimiento() -> None:
    shop = make_shop()
    _expired_payment(
        shop,
        wa_number="59170005551",
        name="Vera",
        public_number="AC-LINK1",
        amount="20.00",
    )
    _quiet_customer(shop, "59170005552", "Omar", days_ago=40)

    body = build_analytics_summary(shop.store, PILOT_TENANT_ID, period="7d", now=NOW)
    by_type = {alert["type"]: alert for alert in body["alerts"]}
    assert by_type["payment_overdue"]["href"] == FOLLOWUP_HREF
    assert by_type["customer_inactive"]["href"] == FOLLOWUP_HREF
