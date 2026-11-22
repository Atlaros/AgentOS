"""Owner manual cash orders and edits. Prices come from the catalog."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from factory_os.domain.models import OrderItem, PaymentStatus, PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client


def _available(client) -> list[dict]:
    products = client.get("/api/catalog?limit=200").json()["products"]
    return [item for item in products if item["available"] and int(item["stock"]) >= 1]


def test_manual_cash_order_persists_confirmed_payment_and_sold_variant() -> None:
    shop = make_shop()
    client = owner_client(shop)
    garment = _available(client)[0]
    created = client.post(
        "/api/orders",
        json={
            "wa_number": "+591 7600-1100",
            "name": "Lucía",
            "address": "Equipetrol",
            "items": [{"variant_sku": garment["variant_sku"], "quantity": 1}],
            "recipient_name": "Lucía",
            "delivery_address": "Equipetrol",
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["payment_status"] == "confirmed"
    assert body["provider"] == "cash"
    assert str(body["provider_ref"]).startswith("cash-")
    assert "baneco" not in str(body["provider_ref"]).lower()

    listed = client.get("/api/orders").json()["orders"]
    row = next(item for item in listed if item["id"] == body["id"])
    assert row["customer_name"] == "Lucía"
    assert row["wa_number"] == "59176001100"
    assert row["payment_status"] == "confirmed"
    assert row["provider"] == "cash"
    assert row["has_delivery"] is True
    assert Decimal(row["items"][0]["unit_price"]) == Decimal(garment["price"])
    assert Decimal(row["total"]) == Decimal(garment["price"])

    payment = shop.store.payment_for_order(PILOT_TENANT_ID, UUID(body["id"]))
    assert payment is not None
    assert payment.provider == "cash"
    assert payment.status is PaymentStatus.CONFIRMED
    assert payment.qr_payload == "CASH"

    movements = client.get("/api/cash").json()["movements"]
    assert any(
        item["direction"] == "in" and row["public_number"] in item["reason"] and "caja" in item["reason"]
        for item in movements
    )
    sold = next(
        item
        for item in client.get("/api/catalog?limit=200").json()["products"]
        if item["variant_sku"] == garment["variant_sku"]
    )
    assert sold["available"] is False
    assert sold["stock"] == 0


def test_mark_cash_paid_on_unpaid_placed_order_consumes_stock() -> None:
    """settle_cash must sell even if the unpaid order was already 'placed'."""
    shop = make_shop()
    client = owner_client(shop)
    garment = next(
        item
        for item in _available(client)
        if int(item["stock"]) == 1
    )
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59176009998")
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem(
            garment["variant_sku"],
            garment["name"],
            1,
            Decimal(garment["price"]),
            garment["currency"],
        ),
        status="placed",
    )
    patched = client.patch(
        f"/api/orders/{order.id}",
        json={"mark_cash_paid": True},
    )
    assert patched.status_code == 200
    assert patched.json()["payment_status"] == "confirmed"
    sold = next(
        item
        for item in client.get("/api/catalog?limit=200").json()["products"]
        if item["variant_sku"] == garment["variant_sku"]
    )
    assert sold["available"] is False
    assert sold["stock"] == 0


def test_manual_cash_order_unknown_sku_is_400() -> None:
    client = owner_client(make_shop())
    missing = client.post(
        "/api/orders",
        json={
            "wa_number": "59176001101",
            "items": [{"variant_sku": "no-such-sku", "quantity": 1}],
        },
    )
    assert missing.status_code == 400
    assert missing.json()["detail"] == "unknown_variant"


def test_patch_order_name_and_address_persist() -> None:
    shop = make_shop()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59176002001")
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("h001-M-VP", "blusa de hilo", 1, Decimal("145.00"), "BOB"),
    )
    client = owner_client(shop)
    patched = client.patch(
        f"/api/orders/{order.id}",
        json={"name": "María", "address": "Calle 4"},
    )
    assert patched.status_code == 200
    row = next(item for item in client.get("/api/orders").json()["orders"] if item["id"] == str(order.id))
    assert row["customer_name"] == "María"
    assert row["location"] == "Calle 4"
    stored = shop.store.get_customer(PILOT_TENANT_ID, customer.id)
    assert stored is not None
    assert stored.name == "María"
    assert stored.address == "Calle 4"


def test_patch_order_items_on_confirmed_payment_is_409() -> None:
    shop = make_shop()
    client = owner_client(shop)
    first, second = _available(client)[:2]
    created = client.post(
        "/api/orders",
        json={
            "wa_number": "59176002002",
            "name": "Ana",
            "items": [{"variant_sku": first["variant_sku"], "quantity": 1}],
        },
    )
    assert created.status_code == 200
    order_id = created.json()["id"]
    locked = client.patch(
        f"/api/orders/{order_id}",
        json={"items": [{"variant_sku": second["variant_sku"], "quantity": 1}]},
    )
    assert locked.status_code == 409
    assert locked.json()["detail"] == "payment_locked"
    row = next(item for item in client.get("/api/orders").json()["orders"] if item["id"] == order_id)
    assert row["items"][0]["variant_sku"] == first["variant_sku"]


def test_patch_order_items_on_unpaid_replaces_catalog_lines() -> None:
    shop = make_shop()
    client = owner_client(shop)
    first, second = _available(client)[:2]
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59176002003")
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem(first["variant_sku"], first["name"], 1, Decimal(first["price"]), first["currency"]),
        status="reserved",
    )
    same = client.patch(
        f"/api/orders/{order.id}",
        json={"items": [{"variant_sku": first["variant_sku"], "quantity": 1}]},
    )
    assert same.status_code == 200
    patched = client.patch(
        f"/api/orders/{order.id}",
        json={"items": [{"variant_sku": second["variant_sku"], "quantity": 1}]},
    )
    assert patched.status_code == 200
    row = next(item for item in client.get("/api/orders").json()["orders"] if item["id"] == str(order.id))
    assert row["items"][0]["variant_sku"] == second["variant_sku"]
    assert Decimal(row["items"][0]["unit_price"]) == Decimal(second["price"])
    assert row["payment_status"] is None
