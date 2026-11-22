"""T7 walk-in QR sale from Caja: Baneco/fake confirm → ticket, not drawer cash (ADR-009)."""

from __future__ import annotations

from decimal import Decimal

from factory_os.domain.models import PILOT_TENANT_ID, PaymentStatus
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"


def test_walkin_qr_sale_confirms_via_adapter_without_drawer_cash_or_order() -> None:
    shop = make_shop()
    client = owner_client(shop)
    orders_before = len(shop.store.list_orders(PILOT_TENANT_ID))

    client.post("/api/cash/session/open", json={"opening_float": "100"})
    before = client.get("/api/cash/session").json()["session"]
    assert before["expected_cash"] == "100.00"

    issued = client.post(
        "/api/cash/sales/qr",
        json={"lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert issued.status_code == 200
    body = issued.json()
    assert body["status"] == "pending_qr"
    assert body["method"] == "qr"
    assert body["number"].startswith("TK-")
    assert body["qr"]
    assert body["provider_ref"]
    assert body.get("order_id") in (None, "")
    assert body["movement_id"] in (None, "")
    # Stock not sold until bank confirms.
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock >= 1
    assert not shop.store.get_variant(PILOT_TENANT_ID, SKU).attributes.get("disabled")

    mid = client.get("/api/cash/session").json()["session"]
    assert mid["expected_cash"] == "100.00"

    confirmed = client.post(
        "/payments/fake-confirm",
        params={"provider_ref": body["provider_ref"]},
    )
    assert confirmed.status_code == 200

    ticket = client.get(f"/api/cash/sales/{body['id']}").json()
    assert ticket["status"] == "recorded"
    assert ticket["method"] == "qr"
    assert ticket["movement_id"] in (None, "")

    variant = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert variant.stock == 0
    assert variant.attributes.get("disabled") is True
    assert len(shop.store.list_orders(PILOT_TENANT_ID)) == orders_before

    payment = shop.store.payment_status(PILOT_TENANT_ID, body["provider_ref"])
    assert payment is not None
    assert payment.status is PaymentStatus.CONFIRMED
    assert payment.order_id is None

    after = client.get("/api/cash/session").json()["session"]
    assert after["expected_cash"] == "100.00"
    assert after["qr_in"] == ticket["total"] or Decimal(after["qr_in"]) == Decimal(ticket["total"])

    closed = client.post(
        "/api/cash/session/close",
        json={"counted_cash": "100.00", "note": ""},
    )
    assert closed.status_code == 200
    assert closed.json()["qr_in"] == ticket["total"] or Decimal(closed.json()["qr_in"]) == Decimal(
        ticket["total"]
    )


def test_walkin_qr_confirm_decrements_quantity() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    shop.store.set_variant_availability(PILOT_TENANT_ID, SKU, available=True, stock=5)
    issued = client.post(
        "/api/cash/sales/qr",
        json={"lines": [{"variant_sku": SKU, "quantity": 2}]},
    )
    assert issued.status_code == 200
    body = issued.json()
    held = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert held is not None
    assert held.stock == 5
    confirmed = client.post("/payments/fake-confirm", params={"provider_ref": body["provider_ref"]})
    assert confirmed.status_code == 200
    variant = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert variant is not None
    assert variant.stock == 3
    assert not variant.attributes.get("disabled")


def test_walkin_qr_requires_open_session() -> None:
    shop = make_shop()
    client = owner_client(shop)
    blocked = client.post(
        "/api/cash/sales/qr",
        json={"lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "session_required"


def test_cancel_pending_walkin_qr_voids_ticket_and_releases_hold() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "50"})

    issued = client.post(
        "/api/cash/sales/qr",
        json={"lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert issued.status_code == 200
    body = issued.json()
    assert body["status"] == "pending_qr"
    assert SKU in shop.store.held_variant_skus(PILOT_TENANT_ID)

    blocked = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "out_of_stock"

    cancelled = client.post(f"/api/cash/sales/{body['id']}/cancel")
    assert cancelled.status_code == 200
    voided = cancelled.json()
    assert voided["status"] == "voided"
    assert voided["id"] == body["id"]
    assert SKU not in shop.store.held_variant_skus(PILOT_TENANT_ID)

    payment = shop.store.payment_status(PILOT_TENANT_ID, body["provider_ref"])
    assert payment is not None
    assert payment.status is not PaymentStatus.PENDING

    sold = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert sold.status_code == 200
    assert sold.json()["status"] == "recorded"


def test_check_pending_walkin_qr_records_after_provider_confirm() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "50"})

    issued = client.post(
        "/api/cash/sales/qr",
        json={"lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert issued.status_code == 200
    body = issued.json()
    assert body["status"] == "pending_qr"
    provider_ref = body["provider_ref"]
    assert provider_ref

    still_pending = client.post(f"/api/cash/sales/{body['id']}/check")
    assert still_pending.status_code == 200
    assert still_pending.json()["status"] == "pending_qr"

    shop.payments.confirm(provider_ref)
    checked = client.post(f"/api/cash/sales/{body['id']}/check")
    assert checked.status_code == 200
    ticket = checked.json()
    assert ticket["status"] == "recorded"
    assert ticket["movement_id"] in (None, "")

    variant = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert variant.stock == 0
    assert variant.attributes.get("disabled") is True
    payment = shop.store.payment_status(PILOT_TENANT_ID, provider_ref)
    assert payment is not None
    assert payment.status is PaymentStatus.CONFIRMED
