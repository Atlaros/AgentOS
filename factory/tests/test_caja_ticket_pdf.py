"""Walk-in sale ticket PDF: commercial receipt, not a fiscal invoice."""

from __future__ import annotations

import pytest

from factory_os.domain.cash_ticket_pdf import _build_receipt_lines, _business_name
from tests.conftest import make_shop, owner_client

SKU_CASH = "h001-M-VP"
SKU_QR = "h002-M-B"


def test_ticket_pdf_cash_walkin_sale_starts_with_pdf_and_contains_number() -> None:
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
    number = ticket["number"]
    assert number

    res = client.get(
        f"/api/cash/activity/{movement_id}/ticket.pdf",
        params={"kind": "cash_movement"},
    )
    assert res.status_code == 200
    assert "application/pdf" in res.headers.get("content-type", "")
    disposition = res.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert f"ticket-{number}.pdf" in disposition
    assert res.content[:4] == b"%PDF"
    assert number.encode("ascii") in res.content
    assert b"COMPROBANTE" in res.content
    assert "No es factura fiscal".encode("latin-1") in res.content


def test_ticket_pdf_confirmed_qr_sale_ok_affects_cash_irrelevant() -> None:
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

    res = client.get(
        f"/api/cash/activity/{qr_body['id']}/ticket.pdf",
        params={"kind": "qr_sale"},
    )
    assert res.status_code == 200
    assert "application/pdf" in res.headers.get("content-type", "")
    assert res.content[:4] == b"%PDF"
    assert qr_body["number"].encode("ascii") in res.content
    assert b"COMPROBANTE" in res.content
    assert "No es factura fiscal".encode("latin-1") in res.content


def test_ticket_pdf_cash_movement_without_ticket_returns_404() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "100"})

    out = client.post(
        "/api/cash",
        json={
            "direction": "out",
            "amount": "10",
            "reason": "gasto manual",
            "category": "gasto",
            "method": "cash",
        },
    )
    assert out.status_code == 200
    movement_id = out.json()["id"]

    res = client.get(
        f"/api/cash/activity/{movement_id}/ticket.pdf",
        params={"kind": "cash_movement"},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "ticket_not_found"


def test_receipt_lines_default_business_and_producto_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CASH_TICKET_BUSINESS_NAME", raising=False)
    monkeypatch.delenv("SHOP_NAME", raising=False)
    assert _business_name() == "Del Campus Café"
    assert "Authentic Closet" not in _business_name()

    lines = _build_receipt_lines(
        {
            "ticket_number": "T-9",
            "amount": "10.00",
            "currency": "BOB",
            "method": "cash",
            "status": "recorded",
            "lines": [
                {
                    "quantity": 2,
                    "unit_price": "5.00",
                    "line_total": "10.00",
                }
            ],
        }
    )
    joined = "\n".join(lines)
    assert "COMPROBANTE DE VENTA" in joined
    assert "No es factura fiscal" in joined
    assert "producto" in joined
    assert "prenda" not in joined
    assert "P.unit" in joined
    assert "Importe" in joined
    assert "TOTAL" in joined


def test_receipt_business_name_prefers_cash_ticket_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOP_NAME", "Otra tienda")
    monkeypatch.setenv("CASH_TICKET_BUSINESS_NAME", "Café del parque")
    assert _business_name() == "Café del parque"
