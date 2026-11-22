"""Slice A: period-scoped report downloads and the catalog cards."""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import StringIO
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from factory_os.domain.models import OrderItem, PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client

WINDOW_FROM = "2026-11-01T00:00:00+00:00"
WINDOW_TO = "2026-11-08T00:00:00+00:00"
INSIDE = datetime(2026, 11, 5, 15, tzinfo=UTC)
OUTSIDE = datetime(2026, 10, 1, 12, tzinfo=UTC)


def _panel_client(shop, secret: str) -> TestClient:
    from factory_os.api.main import create_app
    from tests.conftest import api_settings

    client = TestClient(create_app(shop, api_settings()))
    client.headers["Authorization"] = f"Bearer {secret}"
    return client


def _seed_dated_rows(shop):
    buyer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170004111")
    inside_order = shop.store.create_order(
        PILOT_TENANT_ID,
        buyer.id,
        OrderItem("h001-M-VP", "blusa", 1, Decimal("145.00"), "BOB"),
    )
    inside_order.public_number = "IN-WINDOW"
    inside_order.created_at = INSIDE
    outside_order = shop.store.create_order(
        PILOT_TENANT_ID,
        buyer.id,
        OrderItem("h001-M-VP", "blusa", 1, Decimal("90.00"), "BOB"),
    )
    outside_order.public_number = "OUT-WINDOW"
    outside_order.created_at = OUTSIDE

    inside_payment = shop.store.create_payment(
        PILOT_TENANT_ID,
        inside_order.id,
        "fake",
        "pay-inside",
        Decimal("145.00"),
        "BOB",
        "QR:inside",
        customer_id=buyer.id,
    )
    inside_payment.created_at = INSIDE
    outside_payment = shop.store.create_payment(
        PILOT_TENANT_ID,
        outside_order.id,
        "fake",
        "pay-outside",
        Decimal("90.00"),
        "BOB",
        "QR:outside",
        customer_id=buyer.id,
    )
    outside_payment.created_at = OUTSIDE
    return inside_order, outside_order


def _data_rows(text: str) -> list[list[str]]:
    return list(csv.reader(StringIO(text)))[1:]


def test_report_export_without_dates_keeps_the_full_dump() -> None:
    shop = make_shop()
    _seed_dated_rows(shop)
    client = owner_client(shop)

    orders = client.get("/api/reports/orders.csv")
    payments = client.get("/api/reports/payments.csv")
    assert orders.status_code == 200
    assert payments.status_code == 200
    assert "IN-WINDOW" in orders.text
    assert "OUT-WINDOW" in orders.text
    assert "pay-inside" in payments.text
    assert "pay-outside" in payments.text


def test_report_export_date_range_excludes_rows_outside_the_window() -> None:
    shop = make_shop()
    _seed_dated_rows(shop)
    client = owner_client(shop)
    query = urlencode({"date_from": WINDOW_FROM, "date_to": WINDOW_TO})

    orders = client.get(f"/api/reports/orders.csv?{query}")
    payments = client.get(f"/api/reports/payments?{query}&format=csv")
    assert orders.status_code == 200
    assert payments.status_code == 200
    assert "IN-WINDOW" in orders.text
    assert "OUT-WINDOW" not in orders.text
    assert "pay-inside" in payments.text
    assert "pay-outside" not in payments.text


def test_report_export_period_7d_excludes_older_rows() -> None:
    shop = make_shop()
    buyer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170004112")
    recent = shop.store.create_order(
        PILOT_TENANT_ID,
        buyer.id,
        OrderItem("h001-M-VP", "blusa", 1, Decimal("10.00"), "BOB"),
    )
    recent.public_number = "RECENT-ORDER"
    recent.created_at = datetime.now(UTC) - timedelta(days=1)
    stale = shop.store.create_order(
        PILOT_TENANT_ID,
        buyer.id,
        OrderItem("h001-M-VP", "blusa", 1, Decimal("10.00"), "BOB"),
    )
    stale.public_number = "STALE-ORDER"
    stale.created_at = datetime.now(UTC) - timedelta(days=40)
    recent_payment = shop.store.create_payment(
        PILOT_TENANT_ID,
        recent.id,
        "fake",
        "pay-recent",
        Decimal("10.00"),
        "BOB",
        "QR:recent",
    )
    recent_payment.created_at = recent.created_at
    stale_payment = shop.store.create_payment(
        PILOT_TENANT_ID,
        stale.id,
        "fake",
        "pay-stale",
        Decimal("10.00"),
        "BOB",
        "QR:stale",
    )
    stale_payment.created_at = stale.created_at

    client = owner_client(shop)
    orders = client.get("/api/reports/orders.csv?period=7d")
    payments = client.get("/api/reports/payments.csv?period=7d")
    assert orders.status_code == 200
    assert payments.status_code == 200
    assert "RECENT-ORDER" in orders.text
    assert "STALE-ORDER" not in orders.text
    assert "pay-recent" in payments.text
    assert "pay-stale" not in payments.text


def test_report_catalog_returns_cards_with_period_counts_and_paths() -> None:
    shop = make_shop()
    _seed_dated_rows(shop)
    client = owner_client(shop)
    query = urlencode(
        {"period": "range", "date_from": WINDOW_FROM, "date_to": WINDOW_TO}
    )

    catalog = client.get(f"/api/reports/catalog?{query}")
    assert catalog.status_code == 200
    cards = {card["id"]: card for card in catalog.json()["reports"]}
    assert {"orders", "payments", "stock"} <= set(cards)
    assert {
        "ledger_hechos",
        "journal",
        "mayor",
        "comprobacion",
        "resultado",
        "balance",
    } <= set(cards)

    orders = cards["orders"]
    assert orders["label"]
    assert orders["description"]
    assert "archivo" not in orders["description"].lower()
    assert orders["row_count"] == 1
    assert "date_from=" in orders["downloads"]["csv"]
    assert orders["downloads"]["csv"].startswith("/api/reports/orders")
    assert orders["downloads"]["xlsx"].startswith("/api/reports/orders")
    assert ".xlsx" in orders["downloads"]["xlsx"] or "format=xlsx" in orders["downloads"]["xlsx"]

    payments = cards["payments"]
    assert payments["row_count"] == 1
    assert payments["downloads"]["csv"]
    assert payments["downloads"]["xlsx"]
    assert "archivo" not in payments["description"].lower()

    stock_csv = client.get(f"/api/reports/stock.csv?{query}")
    plain_stock = client.get("/api/reports/stock.csv")
    assert stock_csv.status_code == 200
    assert stock_csv.text == plain_stock.text
    assert cards["stock"]["row_count"] == len(_data_rows(stock_csv.text))
    assert cards["stock"]["row_count"] > 0
    assert "archivo" not in cards["stock"]["description"].lower()

    for report_id in (
        "ledger_hechos",
        "journal",
        "mayor",
        "comprobacion",
        "resultado",
        "balance",
    ):
        card = cards[report_id]
        assert card["label"]
        assert card["description"]
        assert "archivo" not in card["description"].lower()
        assert card["downloads"]["csv"]
        assert card["downloads"]["xlsx"]
        assert not card["downloads"]["csv"].startswith("/api/reports/")
        assert not card["downloads"]["xlsx"].startswith("/api/reports/")


def test_unknown_report_is_404() -> None:
    client = owner_client(make_shop())
    missing = client.get("/api/reports/nope.csv")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "unknown_report"


def test_staff_cannot_download_supervisor_can_alerts_stay_open() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    staff_user = owner.post(
        "/api/panel/users",
        json={
            "name": "Luis Staff",
            "email": "luis-reports@taller.local",
            "role": "staff",
            "secret": "staff-reports",
        },
    )
    assert staff_user.status_code == 200
    supervisor_user = owner.post(
        "/api/panel/users",
        json={
            "name": "Ana Super",
            "email": "ana-reports@taller.local",
            "role": "supervisor",
            "secret": "super-reports",
        },
    )
    assert supervisor_user.status_code == 200

    staff = _panel_client(shop, "staff-reports")
    assert staff.get("/api/reports/orders.csv").status_code == 403
    assert staff.get("/api/reports/catalog").status_code == 403
    assert staff.get("/api/alerts").status_code == 200

    supervisor = _panel_client(shop, "super-reports")
    downloaded = supervisor.get("/api/reports/orders.csv")
    assert downloaded.status_code == 200
    assert "text/csv" in downloaded.headers["content-type"]
    catalog = supervisor.get("/api/reports/catalog?period=7d")
    assert catalog.status_code == 200
    ids = {card["id"] for card in catalog.json()["reports"]}
    assert {"orders", "payments", "stock"} <= ids
    assert {
        "ledger_hechos",
        "journal",
        "mayor",
        "comprobacion",
        "resultado",
        "balance",
    } <= ids


def test_xlsx_format_downloads_a_workbook() -> None:
    client = owner_client(make_shop())
    response = client.get("/api/reports/orders.xlsx")
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    catalog = client.get("/api/reports/catalog?period=7d")
    assert catalog.status_code == 200
    assert catalog.json()["excel_available"] is True
