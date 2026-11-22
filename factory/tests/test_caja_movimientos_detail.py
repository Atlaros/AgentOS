"""T2 Movimientos: entry filters + activity detail (v2-caja-movimientos)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from tests.conftest import make_shop, owner_client

SKU_CASH = "h001-M-VP"
SKU_QR = "h002-M-B"


def test_filter_method_qr_returns_only_qr_entries_balance_unchanged() -> None:
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

    unfiltered = client.get("/api/cash").json()
    filtered = client.get("/api/cash", params={"method": "qr"}).json()

    assert all(e["method"] == "qr" for e in filtered["entries"])
    assert any(e["kind"] == "qr_sale" for e in filtered["entries"])
    assert not any(e.get("ticket_id") == cash_ticket["id"] for e in filtered["entries"])
    assert any(e.get("ticket_id") == qr_body["id"] for e in filtered["entries"])

    # Arqueo stays unfiltered cash (QR filter must not change drawer totals).
    assert Decimal(filtered["in"]) == Decimal(unfiltered["in"])
    assert Decimal(filtered["out"]) == Decimal(unfiltered["out"])
    assert Decimal(filtered["balance"]) == Decimal(unfiltered["balance"])
    assert Decimal(filtered["in"]) == Decimal(cash_ticket["total"])
    assert Decimal(filtered["balance"]) == Decimal(cash_ticket["total"])


def test_activity_detail_cash_walkin_includes_lines() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})

    cash = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU_CASH, "quantity": 1}]},
    )
    assert cash.status_code == 200
    ticket = cash.json()
    movement_id = ticket["movement_id"]
    assert movement_id

    detail = client.get(
        f"/api/cash/activity/{movement_id}",
        params={"kind": "cash_movement"},
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["kind"] == "cash_movement"
    assert body["method"] == "cash"
    assert body["affects_cash"] is True
    assert body["ticket_number"] == ticket["number"]
    assert body["session_id"]
    assert isinstance(body["lines"], list)
    assert len(body["lines"]) >= 1
    line = body["lines"][0]
    assert line["variant_sku"] == SKU_CASH
    assert line["name"]
    assert line["quantity"] == 1
    assert "unit_price" in line
    assert "line_total" in line
    assert "currency" in line


def test_activity_detail_confirmed_qr_includes_lines_affects_cash_false() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})

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

    detail = client.get(
        f"/api/cash/activity/{qr_body['id']}",
        params={"kind": "qr_sale"},
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["kind"] == "qr_sale"
    assert body["method"] == "qr"
    assert body["affects_cash"] is False
    assert body["status"] == "recorded"
    assert body["ticket_number"] == qr_body["number"]
    assert isinstance(body["lines"], list)
    assert len(body["lines"]) >= 1
    assert body["lines"][0]["variant_sku"] == SKU_QR


def test_activity_detail_unknown_id_returns_404() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})

    missing = uuid4()
    res = client.get(
        f"/api/cash/activity/{missing}",
        params={"kind": "cash_movement"},
    )
    assert res.status_code == 404
