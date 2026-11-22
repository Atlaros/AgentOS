"""Slice C: download history, monthly package, and confirmed customer reminders."""

from __future__ import annotations

import csv
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO, StringIO
from uuid import uuid4

from factory_os.domain.models import OrderItem, PILOT_TENANT_ID, PaymentStatus
from factory_os.domain.reports import NOTICE_BODIES
from tests.conftest import make_shop, owner_client
from tests.test_reports_downloads import _panel_client

OCTOBER = datetime(2026, 10, 15, 16, tzinfo=UTC)
SEPTEMBER = datetime(2026, 9, 15, 16, tzinfo=UTC)
NOVEMBER = datetime(2026, 11, 15, 16, tzinfo=UTC)


def _order(shop, buyer, number: str, when: datetime, ref: str):
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        buyer.id,
        OrderItem("h001-M-VP", "blusa", 1, Decimal("40.00"), "BOB"),
    )
    order.public_number = number
    order.created_at = when
    payment = shop.store.create_payment(
        PILOT_TENANT_ID,
        order.id,
        "fake",
        ref,
        Decimal("40.00"),
        "BOB",
        f"QR:{ref}",
        customer_id=buyer.id,
    )
    payment.created_at = when
    return order, payment


def _seed_months(shop):
    buyer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170005001")
    _order(shop, buyer, "OCT-IN", OCTOBER, "pay-oct")
    _order(shop, buyer, "SEP-OUT", SEPTEMBER, "pay-sep")
    _order(shop, buyer, "NOV-OUT", NOVEMBER, "pay-nov")
    return buyer


def _zip_member(blob: bytes, suffix: str) -> tuple[str, str]:
    archive = zipfile.ZipFile(BytesIO(blob))
    matches = [name for name in archive.namelist() if name.endswith(suffix)]
    assert len(matches) == 1
    return matches[0], archive.read(matches[0]).decode()


def _sheet_text(blob: bytes, title: str) -> str:
    from openpyxl import load_workbook

    book = load_workbook(BytesIO(blob))
    lines: list[str] = []
    for row in book[title].iter_rows(values_only=True):
        lines.append(",".join("" if cell is None else str(cell) for cell in row))
    return "\n".join(lines)


def _expired_debtor(shop):
    debtor = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170005010")
    debtor.name = "Marta"
    chat = shop.store.get_or_create_conversation(PILOT_TENANT_ID, debtor)
    shop.store.append_message(chat, "customer", "el qr")
    owed = shop.store.create_order(
        PILOT_TENANT_ID,
        debtor.id,
        OrderItem("h001-M-VP", "blusa", 1, Decimal("145.00"), "BOB"),
    )
    payment = shop.store.create_payment(
        PILOT_TENANT_ID,
        owed.id,
        "fake",
        "pay-expired-c",
        Decimal("145.00"),
        "BOB",
        "QR:expired-c",
        customer_id=debtor.id,
    )
    payment.status = PaymentStatus.EXPIRED
    return debtor, payment


def test_download_records_history_and_list_is_newest_first() -> None:
    shop = make_shop()
    _seed_months(shop)
    client = owner_client(shop)

    first = client.get("/api/reports/orders.csv?period=7d")
    assert first.status_code == 200
    history = client.get("/api/reports/downloads/history")
    assert history.status_code == 200
    rows = history.json()["downloads"]
    assert rows[0]["report_id"] == "orders"
    assert rows[0]["period_id"] == "7d"
    assert rows[0]["format"] == "csv"
    assert rows[0]["actor_name"] == "Dueño"
    assert rows[0]["created_at"]

    second = client.get("/api/reports/payments.csv")
    assert second.status_code == 200
    again = client.get("/api/reports/downloads/history").json()["downloads"]
    assert [row["report_id"] for row in again[:2]] == ["payments", "orders"]
    assert again[0]["period_id"] == ""
    assert again[0]["format"] == "csv"

    missing = client.get("/api/reports/nope.csv")
    assert missing.status_code == 404
    after_miss = client.get("/api/reports/downloads/history").json()["downloads"]
    assert len(after_miss) == len(again)


def test_staff_cannot_read_download_history_supervisor_can() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    assert owner.get("/api/reports/stock.csv").status_code == 200
    staff_user = owner.post(
        "/api/panel/users",
        json={
            "name": "Luis Staff",
            "email": "luis-slice-c@taller.local",
            "role": "staff",
            "secret": "staff-slice-c",
        },
    )
    assert staff_user.status_code == 200
    supervisor_user = owner.post(
        "/api/panel/users",
        json={
            "name": "Ana Super",
            "email": "ana-slice-c@taller.local",
            "role": "supervisor",
            "secret": "super-slice-c",
        },
    )
    assert supervisor_user.status_code == 200

    staff = _panel_client(shop, "staff-slice-c")
    assert staff.get("/api/reports/downloads/history").status_code == 403
    assert staff.get("/api/reports/package?month=2026-10").status_code == 403

    supervisor = _panel_client(shop, "super-slice-c")
    listed = supervisor.get("/api/reports/downloads/history")
    assert listed.status_code == 200
    assert listed.json()["downloads"][0]["report_id"] == "stock"
    downloaded = supervisor.get("/api/reports/orders.csv?period=today")
    assert downloaded.status_code == 200
    newest = supervisor.get("/api/reports/downloads/history").json()["downloads"][0]
    assert newest["actor_name"] == "Ana Super"
    assert newest["report_id"] == "orders"


def test_monthly_zip_package_filters_the_month_and_logs_history() -> None:
    shop = make_shop()
    _seed_months(shop)
    client = owner_client(shop)

    bad = client.get("/api/reports/package?month=2026-13")
    assert bad.status_code == 400
    assert client.get("/api/reports/downloads/history").json()["downloads"] == []

    package = client.get("/api/reports/package?month=2026-10&format=zip")
    assert package.status_code == 200
    assert "zip" in package.headers["content-type"]
    assert "2026-10" in package.headers["content-disposition"]

    orders_name, orders_text = _zip_member(package.content, "orders.csv")
    payments_name, payments_text = _zip_member(package.content, "payments.csv")
    stock_name, stock_text = _zip_member(package.content, "stock.csv")
    assert "2026-10" in orders_name
    assert "2026-10" in payments_name
    assert "2026-10" in stock_name
    assert "OCT-IN" in orders_text
    assert "SEP-OUT" not in orders_text
    assert "NOV-OUT" not in orders_text
    assert "pay-oct" in payments_text
    assert "pay-sep" not in payments_text
    assert "pay-nov" not in payments_text
    assert "h001-M-VP" in stock_text
    assert list(csv.reader(StringIO(stock_text)))[0][0] == "variant_sku"

    logged = client.get("/api/reports/downloads/history").json()["downloads"][0]
    assert logged["report_id"] == "package"
    assert logged["period_id"] == "2026-10"
    assert logged["format"] == "zip"
    assert logged["actor_name"] == "Dueño"


def test_monthly_xlsx_package_has_three_sheets_for_the_month() -> None:
    shop = make_shop()
    _seed_months(shop)
    client = owner_client(shop)
    catalog = client.get("/api/reports/catalog?period=month")
    assert catalog.status_code == 200
    assert catalog.json()["excel_available"] is True

    package = client.get("/api/reports/package?month=2026-10&format=xlsx")
    assert package.status_code == 200
    assert "spreadsheetml" in package.headers["content-type"]
    orders = _sheet_text(package.content, "Ventas")
    payments = _sheet_text(package.content, "Cobros")
    stock = _sheet_text(package.content, "Inventario")
    assert "OCT-IN" in orders
    assert "SEP-OUT" not in orders
    assert "pay-oct" in payments
    assert "pay-nov" not in payments
    assert "h001-M-VP" in stock

    logged = client.get("/api/reports/downloads/history").json()["downloads"][0]
    assert logged["report_id"] == "package"
    assert logged["format"] == "xlsx"


def test_single_xlsx_download_is_a_workbook_and_is_logged() -> None:
    shop = make_shop()
    _seed_months(shop)
    client = owner_client(shop)
    workbook = client.get("/api/reports/orders.xlsx?period=month")
    assert workbook.status_code == 200
    assert "spreadsheetml" in workbook.headers["content-type"]
    text = _sheet_text(workbook.content, "Ventas")
    assert "public_number" in text
    logged = client.get("/api/reports/downloads/history").json()["downloads"][0]
    assert logged["report_id"] == "orders"
    assert logged["format"] == "xlsx"
    assert logged["period_id"] == "month"


def test_reminder_preview_returns_the_notice_and_does_not_send() -> None:
    shop = make_shop()
    debtor, payment = _expired_debtor(shop)
    client = owner_client(shop)

    preview = client.post("/api/reminders/preview", json={"customer_id": str(debtor.id)})
    assert preview.status_code == 200
    body = preview.json()
    assert body["would_send"] is True
    assert body["kind"] == "collections"
    assert body["body"] == NOTICE_BODIES["collections"]
    assert body["wa_number"] == debtor.wa_number
    assert body["customer_label"] == "Marta"
    assert shop.channel.sent == []
    assert all(item.sent_at is None for item in shop.store.list_reminders(PILOT_TENANT_ID))
    assert shop.store.get_payment(PILOT_TENANT_ID, payment.id).status is PaymentStatus.EXPIRED

    wrong = client.post(
        "/api/reminders/preview",
        json={"customer_id": str(debtor.id), "kind": "follow_up"},
    )
    assert wrong.status_code == 400
    assert wrong.json()["detail"] == "no_notice"

    quiet = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170005011")
    none = client.post("/api/reminders/preview", json={"customer_id": str(quiet.id)})
    assert none.status_code == 400
    assert none.json()["detail"] == "no_notice"
    missing = client.post("/api/reminders/preview", json={"customer_id": str(uuid4())})
    assert missing.status_code == 400
    assert missing.json()["detail"] == "no_notice"
    assert shop.channel.sent == []


def test_reminder_send_requires_confirm_and_does_not_confirm_payment() -> None:
    shop = make_shop()
    debtor, payment = _expired_debtor(shop)
    client = owner_client(shop)

    refused = client.post(
        "/api/reminders/send",
        json={"customer_id": str(debtor.id), "kind": "collections"},
    )
    assert refused.status_code == 400
    assert shop.channel.sent == []
    assert all(item.sent_at is None for item in shop.store.list_reminders(PILOT_TENANT_ID))
    assert shop.store.get_payment(PILOT_TENANT_ID, payment.id).status is PaymentStatus.EXPIRED

    explicit = client.post(
        "/api/reminders/send",
        json={"customer_id": str(debtor.id), "kind": "collections", "confirm": False},
    )
    assert explicit.status_code == 400
    assert shop.channel.sent == []

    sent = client.post(
        "/api/reminders/send",
        json={"customer_id": str(debtor.id), "kind": "collections", "confirm": True},
    )
    assert sent.status_code == 200
    reminders = [
        item
        for item in shop.store.list_reminders(PILOT_TENANT_ID)
        if item.customer_id == debtor.id and item.kind == "collections"
    ]
    assert reminders
    assert reminders[-1].sent_at is not None
    assert shop.channel.sent == [(debtor.wa_number, NOTICE_BODIES["collections"])]
    assert "145" not in shop.channel.sent[0][1]
    assert shop.store.get_payment(PILOT_TENANT_ID, payment.id).status is PaymentStatus.EXPIRED


def test_staff_cannot_preview_or_send_a_customer_reminder() -> None:
    shop = make_shop()
    debtor, payment = _expired_debtor(shop)
    owner = owner_client(shop)
    created = owner.post(
        "/api/panel/users",
        json={
            "name": "Luis Staff",
            "email": "luis-remind@taller.local",
            "role": "staff",
            "secret": "staff-remind",
        },
    )
    assert created.status_code == 200
    staff = _panel_client(shop, "staff-remind")
    preview = staff.post("/api/reminders/preview", json={"customer_id": str(debtor.id)})
    send = staff.post(
        "/api/reminders/send",
        json={"customer_id": str(debtor.id), "kind": "collections", "confirm": True},
    )
    assert preview.status_code == 403
    assert send.status_code == 403
    assert shop.channel.sent == []
    assert shop.store.get_payment(PILOT_TENANT_ID, payment.id).status is PaymentStatus.EXPIRED
