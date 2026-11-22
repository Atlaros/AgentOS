"""T1 Movimientos feed: unified cash + QR session activity (v2-caja-movimientos)."""

from __future__ import annotations

from decimal import Decimal

from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client

SKU_CASH = "h001-M-VP"
SKU_QR = "h002-M-B"


def test_feed_includes_cash_sale_and_confirmed_qr_without_changing_balance() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "100"})

    cash = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU_CASH, "quantity": 1}]},
    )
    assert cash.status_code == 200
    cash_ticket = cash.json()

    qr = client.post(
        "/api/cash/sales/qr",
        json={"lines": [{"variant_sku": SKU_QR, "quantity": 1}]},
    )
    assert qr.status_code == 200
    qr_body = qr.json()
    confirmed = client.post(
        "/payments/fake-confirm",
        params={"provider_ref": qr_body["provider_ref"]},
    )
    assert confirmed.status_code == 200

    book = client.get("/api/cash")
    assert book.status_code == 200
    data = book.json()

    assert "entries" in data
    entries = data["entries"]
    kinds = {e["kind"] for e in entries}
    assert "cash_movement" in kinds
    assert "qr_sale" in kinds

    cash_entry = next(e for e in entries if e.get("ticket_id") == cash_ticket["id"])
    assert cash_entry["kind"] == "cash_movement"
    assert cash_entry["method"] == "cash"
    assert cash_entry["affects_cash"] is True
    assert cash_entry["ticket_number"] == cash_ticket["number"]
    assert cash_entry["movement_id"] == cash_ticket["movement_id"]
    assert cash_entry["summary"]

    qr_entry = next(e for e in entries if e.get("ticket_id") == qr_body["id"])
    assert qr_entry["kind"] == "qr_sale"
    assert qr_entry["method"] == "qr"
    assert qr_entry["affects_cash"] is False
    assert qr_entry["status"] == "recorded"
    assert qr_entry["movement_id"] in (None, "")

    # QR must not inflate drawer cash totals.
    assert Decimal(data["in"]) == Decimal(cash_ticket["total"])
    assert Decimal(data["balance"]) == Decimal(cash_ticket["total"])
    assert Decimal(data["out"]) == Decimal("0")
    # Backward-compat cash-only list still present.
    assert any(m["id"] == cash_ticket["movement_id"] for m in data["movements"])
    assert not any(m.get("ticket_id") == qr_body["id"] for m in data["movements"])


def test_pending_qr_appears_in_feed_with_pending_status() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "50"})

    qr = client.post(
        "/api/cash/sales/qr",
        json={"lines": [{"variant_sku": SKU_QR, "quantity": 1}]},
    )
    assert qr.status_code == 200
    qr_body = qr.json()

    data = client.get("/api/cash").json()
    entry = next(e for e in data["entries"] if e.get("ticket_id") == qr_body["id"])
    assert entry["kind"] == "qr_sale"
    assert entry["status"] == "pending_qr"
    assert entry["affects_cash"] is False
    assert entry["method"] == "qr"
    assert Decimal(data["in"]) == Decimal("0")
    assert Decimal(data["balance"]) == Decimal("0")


def test_cash_ticket_with_movement_is_not_duplicated() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})

    cash = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU_CASH, "quantity": 1}]},
    )
    assert cash.status_code == 200
    ticket = cash.json()

    data = client.get("/api/cash").json()
    matching = [e for e in data["entries"] if e.get("ticket_id") == ticket["id"]]
    assert len(matching) == 1
    assert matching[0]["kind"] == "cash_movement"
    assert matching[0]["ticket_number"] == ticket["number"]
    assert matching[0]["summary"]
    # No second row for the same ticket as qr_sale / duplicate kind.
    assert not any(
        e["kind"] == "qr_sale" and e.get("ticket_id") == ticket["id"] for e in data["entries"]
    )


def test_default_session_scope_picks_open_session() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "10"})
    open_id = client.get("/api/cash/session").json()["session"]["id"]

    client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU_CASH, "quantity": 1}]},
    )

    data = client.get("/api/cash").json()
    assert data["session"] is not None
    assert data["session"]["id"] == open_id
    assert data["session"]["status"] == "open"
    assert any(e["kind"] == "cash_movement" for e in data["entries"])


def test_default_scope_with_only_closed_session_returns_that_session_entries() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "20"})
    sale = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU_CASH, "quantity": 1}]},
    )
    assert sale.status_code == 200
    ticket = sale.json()
    session_before = client.get("/api/cash").json()["session"]
    session_id = session_before["id"]

    closed = client.post(
        "/api/cash/session/close",
        json={"counted_cash": session_before["expected_cash"], "note": ""},
    )
    assert closed.status_code == 200
    assert client.get("/api/cash/session").json()["session"] is None

    data = client.get("/api/cash").json()
    assert data["session"] is not None
    assert data["session"]["id"] == session_id
    assert data["session"]["status"] == "closed"
    assert any(e.get("ticket_id") == ticket["id"] for e in data["entries"])
    assert Decimal(data["in"]) == Decimal(ticket["total"])

    # Explicit session_id still works.
    scoped = client.get("/api/cash", params={"session_id": session_id}).json()
    assert scoped["session"]["id"] == session_id
    assert any(e.get("ticket_id") == ticket["id"] for e in scoped["entries"])
