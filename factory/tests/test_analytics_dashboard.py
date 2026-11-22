"""T1 Analítica: one summary, confirmed revenue, typed alerts, tenant thresholds."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from factory_os.api.main import create_app
from factory_os.contracts.employees import EmployeeRole, identity_for
from factory_os.domain.analytics import build_analytics_summary
from factory_os.domain.models import (
    PILOT_TENANT_ID,
    CashMovement,
    CashSaleTicket,
    OrderItem,
    PaymentStatus,
)
from factory_os.domain.suppliers import list_low_stock
from tests.conftest import api_settings, make_shop, owner_client

NOW = datetime(2026, 11, 11, 12, tzinfo=UTC)
CURRENT_AT = datetime(2026, 11, 8, 12, tzinfo=UTC)
PREVIOUS_AT = datetime(2026, 10, 30, 12, tzinfo=UTC)


def _client(shop, secret: str) -> TestClient:
    client = TestClient(create_app(shop, api_settings()))
    client.headers["Authorization"] = f"Bearer {secret}"
    return client


def _kpi(body: dict, kpi_id: str) -> dict:
    return next(item for item in body["kpis"] if item["id"] == kpi_id)


def _pay(shop, when: datetime, amount: str, status: PaymentStatus, *, order_status: str = "placed"):
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, f"5917{uuid4().hex[:8]}")
    money = Decimal(amount)
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("h001-M-VP", "blusa", 1, money, "BOB"),
        status=order_status,
    )
    order.created_at = when
    payment = shop.store.create_payment(
        PILOT_TENANT_ID,
        order.id,
        "fake",
        f"pay-{uuid4().hex[:10]}",
        money,
        "BOB",
        "QR:test",
        customer_id=customer.id,
    )
    payment.status = status
    payment.created_at = when
    return order, payment


def test_summary_period_delta_against_previous_equal_window() -> None:
    shop = make_shop()
    _pay(shop, PREVIOUS_AT, "100.00", PaymentStatus.CONFIRMED)
    _pay(shop, CURRENT_AT, "150.00", PaymentStatus.CONFIRMED)
    reserved = shop.store.create_order(
        PILOT_TENANT_ID,
        shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170009999").id,
        OrderItem("h001-M-VP", "blusa", 1, Decimal("10.00"), "BOB"),
        status="reserved",
    )
    reserved.created_at = CURRENT_AT

    body = build_analytics_summary(shop.store, PILOT_TENANT_ID, period="7d", now=NOW)
    assert body["period"]["id"] == "7d"
    assert body["period"]["basis"] == "rolling_7x24h"
    revenue = _kpi(body, "revenue")
    sales = _kpi(body, "sales")
    assert revenue["current"] == "150.00"
    assert revenue["previous"] == "100.00"
    assert revenue["pct_change"] == 50.0
    assert sales["current"] == 1
    assert sales["previous"] == 1
    assert sales["pct_change"] == 0.0
    assert body["orders"] == 1
    assert body["confirmed_amount"] == "150.00"


def test_revenue_counts_confirmed_payments_and_excludes_voided() -> None:
    shop = make_shop()
    _pay(shop, CURRENT_AT, "150.00", PaymentStatus.CONFIRMED)
    _pay(shop, CURRENT_AT, "999.00", PaymentStatus.PENDING)
    _pay(shop, CURRENT_AT, "70.00", PaymentStatus.EXPIRED)
    _voided_order, voided_payment = _pay(shop, CURRENT_AT, "80.00", PaymentStatus.CONFIRMED)
    voided_ticket = CashSaleTicket(
        id=uuid4(),
        tenant_id=PILOT_TENANT_ID,
        number="T-VOID",
        status="voided",
        method="qr",
        total=Decimal("80.00"),
        currency="BOB",
        payment_id=voided_payment.id,
        created_at=CURRENT_AT,
    )
    shop.store.cash_sale_tickets[voided_ticket.id] = voided_ticket

    voided_movement = CashMovement(
        id=uuid4(),
        tenant_id=PILOT_TENANT_ID,
        direction="in",
        amount=Decimal("40.00"),
        currency="BOB",
        reason="anulada",
        status="voided",
        category="venta",
        created_at=CURRENT_AT,
    )
    shop.store.cash[voided_movement.id] = voided_movement
    voided_cash = CashSaleTicket(
        id=uuid4(),
        tenant_id=PILOT_TENANT_ID,
        number="T-CASH-VOID",
        status="recorded",
        method="cash",
        total=Decimal("40.00"),
        currency="BOB",
        movement_id=voided_movement.id,
        created_at=CURRENT_AT,
    )
    shop.store.cash_sale_tickets[voided_cash.id] = voided_cash

    recorded_movement = CashMovement(
        id=uuid4(),
        tenant_id=PILOT_TENANT_ID,
        direction="in",
        amount=Decimal("25.00"),
        currency="BOB",
        reason="ticket caja",
        status="recorded",
        category="venta",
        created_at=CURRENT_AT,
    )
    shop.store.cash[recorded_movement.id] = recorded_movement
    recorded_cash = CashSaleTicket(
        id=uuid4(),
        tenant_id=PILOT_TENANT_ID,
        number="T-CASH-OK",
        status="recorded",
        method="cash",
        total=Decimal("25.00"),
        currency="BOB",
        movement_id=recorded_movement.id,
        created_at=CURRENT_AT,
    )
    shop.store.cash_sale_tickets[recorded_cash.id] = recorded_cash

    body = build_analytics_summary(shop.store, PILOT_TENANT_ID, period="7d", now=NOW)
    revenue = _kpi(body, "revenue")
    # 150 confirmed + 25 recorded cash ticket. Pending, expired, and voided stay out.
    assert revenue["current"] == "175.00"
    assert revenue["previous_empty"] is True
    assert revenue["pct_change"] is None
    assert _kpi(body, "sales")["current"] == 2


def test_empty_period_does_not_invent_a_percent() -> None:
    shop = make_shop()
    body = build_analytics_summary(shop.store, PILOT_TENANT_ID, period="7d", now=NOW)
    revenue = _kpi(body, "revenue")
    sales = _kpi(body, "sales")
    assert revenue["current"] == "0.00"
    assert revenue["previous"] == "0.00"
    assert revenue["pct_change"] is None
    assert revenue["current_empty"] is True
    assert revenue["previous_empty"] is True
    assert sales["current"] == 0
    assert sales["pct_change"] is None
    assert body["payments_confirmed"] == 0


def test_alert_types_are_not_row_spam_and_low_stock_uses_reorder_threshold() -> None:
    shop = make_shop()
    records = list(shop.store.iter_variants())
    assert len(records) >= 3
    for record in records:
        record.stock = 8
        record.reorder_threshold = 1
    sold, unsold, watched = records[0], records[1], records[2]
    sold.stock = 0
    unsold.stock = 0
    watched.stock = 2
    watched.reorder_threshold = 5

    _order, _payment = _pay(shop, CURRENT_AT, "20.00", PaymentStatus.CONFIRMED)
    _order.items[0].variant_sku = sold.variant_sku
    _pay(shop, CURRENT_AT, "10.00", PaymentStatus.EXPIRED)
    stale_order, stale_payment = _pay(shop, NOW - timedelta(hours=30), "5.00", PaymentStatus.PENDING)
    stale_payment.created_at = NOW - timedelta(hours=30)
    assert stale_order.id

    quiet = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170003001")
    quiet_chat = shop.store.get_or_create_conversation(PILOT_TENANT_ID, quiet)
    shop.store.append_message(quiet_chat, "customer", "hola")
    quiet_chat.last_message_at = NOW - timedelta(days=40)
    recent = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170003002")
    recent_chat = shop.store.get_or_create_conversation(PILOT_TENANT_ID, recent)
    shop.store.append_message(recent_chat, "customer", "sigo")
    recent_chat.last_message_at = NOW

    body = build_analytics_summary(shop.store, PILOT_TENANT_ID, period="7d", now=NOW)
    types = [alert["type"] for alert in body["alerts"]]
    assert types.count("low_stock") == 1
    assert len(types) == len(set(types))
    by_type = {alert["type"]: alert for alert in body["alerts"]}
    assert by_type["low_stock"]["count"] == len(list_low_stock(shop.store)) == 3
    assert by_type["low_stock"]["href"] == "/suppliers?tab=reposicion"
    assert by_type["zero_stock_sales"]["count"] == 1
    assert by_type["zero_stock_sales"]["href"] == "/suppliers?tab=reposicion"
    assert by_type["payment_overdue"]["count"] == 1
    assert by_type["payment_overdue"]["href"] == "/reports?tab=seguimiento"
    assert by_type["customer_inactive"]["count"] == 1
    assert by_type["customer_inactive"]["href"] == "/reports?tab=seguimiento"
    assert by_type["qr_pending_stale"]["count"] == 1
    assert by_type["qr_pending_stale"]["href"] == "/orders"
    assert body["alert_type_count"] == len(body["alerts"]) == 5


def test_staff_cannot_read_metrics_supervisor_and_owner_can() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    staff_user = owner.post(
        "/api/panel/users",
        json={
            "name": "Luis Staff",
            "email": "luis-analytics@taller.local",
            "role": "staff",
            "secret": "staff-analytics",
        },
    )
    assert staff_user.status_code == 200
    supervisor_user = owner.post(
        "/api/panel/users",
        json={
            "name": "Ana Super",
            "email": "ana-analytics@taller.local",
            "role": "supervisor",
            "secret": "super-analytics",
        },
    )
    assert supervisor_user.status_code == 200

    staff = _client(shop, "staff-analytics")
    assert staff.get("/api/metrics").status_code == 403
    assert staff.get("/api/analytics/thresholds").status_code == 403
    assert staff.patch("/api/analytics/thresholds", json={"inactive_days": 10}).status_code == 403
    # Reportes sigue abierto al equipo: /api/alerts no se cierra en T1.
    assert staff.get("/api/alerts").status_code == 200

    supervisor = _client(shop, "super-analytics")
    assert supervisor.get("/api/metrics").status_code == 200
    visible = supervisor.get("/api/analytics/thresholds")
    assert visible.status_code == 200
    assert visible.json()["can_edit"] is False
    assert "digest_destinations" not in visible.json()
    assert supervisor.patch("/api/analytics/thresholds", json={"inactive_days": 10}).status_code == 403
    owner_view = owner.get("/api/analytics/thresholds")
    assert owner_view.status_code == 200
    assert owner_view.json()["can_edit"] is True
    assert owner.get("/api/metrics").status_code == 200


def test_thresholds_get_patch_and_drive_qr_and_inactive_alerts() -> None:
    shop = make_shop()
    client = owner_client(shop)
    fresh = client.get("/api/analytics/thresholds")
    assert fresh.status_code == 200
    assert fresh.json()["qr_pending_hours"] == 24
    assert fresh.json()["inactive_days"] == 30
    assert "Proveedores" in fresh.json()["stock_note"]

    _order, pending = _pay(shop, NOW - timedelta(hours=30), "15.00", PaymentStatus.PENDING)
    pending.created_at = NOW - timedelta(hours=30)
    quiet = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170008881")
    chat = shop.store.get_or_create_conversation(PILOT_TENANT_ID, quiet)
    shop.store.append_message(chat, "customer", "hace un rato")
    chat.last_message_at = NOW - timedelta(days=20)

    before = client.get("/api/metrics", params={"period": "7d", "now": NOW.isoformat()})
    assert before.status_code == 200
    before_types = {alert["type"] for alert in before.json()["alerts"]}
    assert "qr_pending_stale" in before_types
    assert "customer_inactive" not in before_types

    patched = client.patch(
        "/api/analytics/thresholds",
        json={"qr_pending_hours": 48, "inactive_days": 10},
    )
    assert patched.status_code == 200
    assert patched.json()["qr_pending_hours"] == 48
    assert patched.json()["inactive_days"] == 10
    again = client.get("/api/analytics/thresholds")
    assert again.json()["qr_pending_hours"] == 48
    assert again.json()["inactive_days"] == 10

    after = client.get("/api/metrics", params={"period": "7d", "now": NOW.isoformat()})
    after_types = {alert["type"] for alert in after.json()["alerts"]}
    assert "qr_pending_stale" not in after_types
    assert "customer_inactive" in after_types
    alerts = client.get("/api/alerts")
    assert alerts.status_code == 200
    assert any(row["id"] == str(quiet.id) for row in alerts.json()["inactive_customers"])

    rejected = client.patch("/api/analytics/thresholds", json={"qr_pending_hours": 0})
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "bad_qr_pending_hours"
    kept = client.get("/api/analytics/thresholds")
    assert kept.json()["qr_pending_hours"] == 48


def test_windows_share_no_instant_and_labels_do_not_imply_overlap() -> None:
    """Half-open facts stay start <= t < end. Printed days must not share a calendar day."""
    import re

    shop = make_shop()
    # 16:00 UTC is 12:00 in America/La_Paz, so "today" and "7d" both cross a calendar join.
    now = datetime(2026, 11, 11, 16, 0, tzinfo=UTC)
    for period in ("today", "7d"):
        body = build_analytics_summary(shop.store, PILOT_TENANT_ID, period=period, now=now)
        window = body["period"]
        start = datetime.fromisoformat(window["start"])
        end = datetime.fromisoformat(window["end"])
        previous_start = datetime.fromisoformat(window["previous_start"])
        previous_end = datetime.fromisoformat(window["previous_end"])
        last_previous = datetime.fromisoformat(window["previous_end_inclusive"])

        assert previous_end == start
        assert previous_start <= last_previous < previous_end
        assert last_previous == previous_end - timedelta(microseconds=1)
        assert not (start <= last_previous < end)
        assert start <= start < end
        assert not (previous_start <= start < previous_end)

        line = f"{window['label_current']} frente a {window['label_previous']}"
        current_label, previous_label = line.split(" frente a ")
        current_days = set(re.findall(r"\d{1,2} [a-z]{3}", current_label))
        previous_days = set(re.findall(r"\d{1,2} [a-z]{3}", previous_label))
        assert current_days
        assert previous_days
        assert current_days.isdisjoint(previous_days), line


def test_owner_patch_thresholds_and_masked_destinations() -> None:
    shop = make_shop()
    shop.owner_numbers = ["59170009999"]
    client = owner_client(shop)
    fresh = client.get("/api/analytics/thresholds")
    assert fresh.status_code == 200
    assert fresh.json()["can_edit"] is True
    assert fresh.json()["digest_destinations"] == ["•••9999"]
    assert "59170009999" not in str(fresh.json()["digest_destinations"])

    patched = client.patch("/api/analytics/thresholds", json={"inactive_days": 12})
    assert patched.status_code == 200
    assert patched.json()["inactive_days"] == 12
    assert patched.json()["can_edit"] is True


def test_metrics_summary_matches_api_for_the_same_period() -> None:
    shop = make_shop()
    _pay(shop, CURRENT_AT, "40.00", PaymentStatus.CONFIRMED)
    client = owner_client(shop)
    api_body = client.get("/api/metrics", params={"period": "7d", "now": NOW.isoformat()}).json()
    tool_body = shop.tools.execute(
        identity_for(EmployeeRole.ANALYST, PILOT_TENANT_ID),
        "metrics.summary",
        {"period": "7d", "now": NOW.isoformat()},
    )
    assert tool_body == api_body
    assert _kpi(tool_body, "revenue")["current"] == "40.00"
    assert "kpis" in tool_body and "alerts" in tool_body and "alert_type_count" in tool_body
    assert "payments_confirmed" not in {item["id"] for item in tool_body["kpis"]}
    assert "payments_confirmed" in tool_body


def _cash_ticket(shop, when: datetime, amount: str, **extra):
    ticket = CashSaleTicket(
        id=uuid4(),
        tenant_id=PILOT_TENANT_ID,
        number=f"T-{uuid4().hex[:6]}",
        status="recorded",
        method="cash",
        total=Decimal(amount),
        currency="BOB",
        created_at=when,
        **extra,
    )
    shop.store.cash_sale_tickets[ticket.id] = ticket
    return ticket


def test_revenue_cash_and_qr_split_sums_to_revenue() -> None:
    shop = make_shop()
    _pay(shop, CURRENT_AT, "150.00", PaymentStatus.CONFIRMED)
    _cash_ticket(shop, CURRENT_AT, "25.00")
    _linked_order, linked_payment = _pay(shop, CURRENT_AT, "40.00", PaymentStatus.CONFIRMED)
    assert _linked_order.id
    _cash_ticket(shop, CURRENT_AT, "40.00", payment_id=linked_payment.id)

    body = build_analytics_summary(shop.store, PILOT_TENANT_ID, period="7d", now=NOW)
    breakdown = body["revenue_breakdown"]
    revenue = _kpi(body, "revenue")
    assert breakdown == {"cash": "25.00", "qr": "190.00"}
    assert Decimal(breakdown["cash"]) + Decimal(breakdown["qr"]) == Decimal(revenue["current"])
    assert body["series"]["tender"] == breakdown
    assert body["payments_confirmed"] == 2
    assert "payments_confirmed" not in {item["id"] for item in body["kpis"]}


def test_avg_ticket_uses_revenue_over_sales_and_stays_empty_without_sales() -> None:
    shop = make_shop()
    _pay(shop, PREVIOUS_AT, "100.00", PaymentStatus.CONFIRMED)
    _pay(shop, CURRENT_AT, "150.00", PaymentStatus.CONFIRMED)
    body = build_analytics_summary(shop.store, PILOT_TENANT_ID, period="7d", now=NOW)
    ticket = _kpi(body, "avg_ticket")
    assert ticket["label"] == "Ticket promedio"
    assert ticket["kind"] == "money"
    assert ticket["current"] == "150.00"
    assert ticket["previous"] == "100.00"
    assert ticket["pct_change"] == 50.0
    assert ticket["current_empty"] is False

    empty = build_analytics_summary(make_shop().store, PILOT_TENANT_ID, period="7d", now=NOW)
    blank = _kpi(empty, "avg_ticket")
    assert blank["current_empty"] is True
    assert blank["previous_empty"] is True
    assert blank["current"] is None
    assert blank["previous"] is None
    assert blank["pct_change"] is None


def test_profit_is_missing_costs_when_the_tenant_has_no_purchases() -> None:
    shop = make_shop()
    _pay(shop, CURRENT_AT, "150.00", PaymentStatus.CONFIRMED)
    body = build_analytics_summary(shop.store, PILOT_TENANT_ID, period="7d", now=NOW)
    profit = _kpi(body, "profit")
    assert profit["label"] == "Utilidad"
    assert profit["kind"] == "money"
    assert profit["current_empty"] is True
    assert profit["unavailable_reason"] == "missing_costs"
    assert profit["current"] is None
    assert profit["pct_change"] is None


def test_profit_subtracts_weighted_cost_when_every_sold_sku_has_one() -> None:
    shop = make_shop()
    _pay(shop, CURRENT_AT, "150.00", PaymentStatus.CONFIRMED)
    shop.store.receive_purchase(PILOT_TENANT_ID, "h001-M-VP", 2, Decimal("40.00"), "BOB")
    body = build_analytics_summary(shop.store, PILOT_TENANT_ID, period="7d", now=NOW)
    profit = _kpi(body, "profit")
    assert profit["current"] == "110.00"
    assert profit.get("unavailable_reason") is None
    assert profit["current_empty"] is False


def test_profit_unavailable_when_a_sold_sku_has_no_cost() -> None:
    shop = make_shop()
    _pay(shop, CURRENT_AT, "150.00", PaymentStatus.CONFIRMED)
    other = next(
        record.variant_sku
        for record in shop.store.iter_variants()
        if record.variant_sku != "h001-M-VP"
    )
    shop.store.receive_purchase(PILOT_TENANT_ID, other, 1, Decimal("10.00"), "BOB")
    body = build_analytics_summary(shop.store, PILOT_TENANT_ID, period="7d", now=NOW)
    profit = _kpi(body, "profit")
    assert profit["unavailable_reason"] == "missing_costs"
    assert profit["current"] is None


def test_sales_by_day_covers_each_local_day_and_sums_to_sales() -> None:
    shop = make_shop()
    _pay(shop, CURRENT_AT, "150.00", PaymentStatus.CONFIRMED)
    _cash_ticket(shop, CURRENT_AT, "25.00")
    body = build_analytics_summary(shop.store, PILOT_TENANT_ID, period="7d", now=NOW)
    days = body["series"]["sales_by_day"]
    assert [row["day"] for row in days][0] == "2026-11-04"
    assert days[-1]["day"] == "2026-11-11"
    assert len(days) == 8
    assert sum(row["current"] for row in days) == _kpi(body, "sales")["current"]
    assert any(row["current"] == 0 for row in days)
    assert all("previous" in row for row in days)

    today = build_analytics_summary(shop.store, PILOT_TENANT_ID, period="today", now=NOW)
    assert len(today["series"]["sales_by_day"]) == 1
    assert today["series"]["sales_by_day"][0]["day"] == "2026-11-11"
