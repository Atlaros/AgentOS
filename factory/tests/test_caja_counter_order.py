"""T2 counter order and open table (ADR-009 amendment)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.order_hold import release_expired_unpaid_orders
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"


def test_cash_sale_creates_counter_order_not_a_chat_order() -> None:
    shop = make_shop()
    client = owner_client(shop)
    before = len(shop.store.list_orders(PILOT_TENANT_ID))
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    shop.store.set_variant_availability(PILOT_TENANT_ID, SKU, available=True, stock=5)

    sale = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU, "quantity": 2}]},
    )
    assert sale.status_code == 200
    body = sale.json()
    assert body["order_id"]
    orders = shop.store.list_orders(PILOT_TENANT_ID)
    assert len(orders) == before + 1
    order = next(item for item in orders if str(item.id) == body["order_id"])
    assert order.origin == "counter"
    assert order.status == "placed"
    assert order.table_label == ""
    assert order.items[0].quantity == 2
    variant = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert variant is not None
    assert variant.stock == 3

    listed = client.get("/api/orders")
    assert listed.status_code == 200
    assert body["order_id"] not in {row["id"] for row in listed.json()["orders"]}


def test_open_table_holds_stock_survives_expiry_and_charge_moves_cash() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "10"})
    shop.store.set_variant_availability(PILOT_TENANT_ID, SKU, available=True, stock=5)

    opened = client.post(
        "/api/cash/tabs",
        json={"table": "Mesa 4", "lines": [{"variant_sku": SKU, "quantity": 2}]},
    )
    assert opened.status_code == 200
    tab = opened.json()
    assert tab["origin"] == "counter"
    assert tab["status"] == "open"
    assert tab["table_label"] == "Mesa 4"
    variant = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert variant is not None
    assert variant.stock == 3
    assert SKU not in shop.store.held_variant_skus(PILOT_TENANT_ID)
    open_tabs = client.get("/api/cash/tabs")
    assert open_tabs.status_code == 200
    assert tab["id"] in {row["id"] for row in open_tabs.json()["tabs"]}
    book = client.get("/api/cash").json()
    assert book["movements"] == [] or all(m["category"] != "venta" for m in book["movements"])

    release_expired_unpaid_orders(
        shop.store, PILOT_TENANT_ID, now=datetime.now(UTC) + timedelta(hours=5)
    )
    still = shop.store.get_order(PILOT_TENANT_ID, UUID(tab["id"]))
    assert still is not None
    assert still.status == "open"
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == 3

    cancelled = client.post(f"/api/cash/tabs/{tab['id']}/cancel")
    assert cancelled.status_code == 200
    assert shop.store.get_order(PILOT_TENANT_ID, still.id).status == "cancelled"
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == 5

    reopened = client.post(
        "/api/cash/tabs",
        json={"table": "Mesa 4", "lines": [{"variant_sku": SKU, "quantity": 2}]},
    )
    assert reopened.status_code == 200
    tab_id = reopened.json()["id"]
    charged = client.post(f"/api/cash/tabs/{tab_id}/charge", json={"method": "cash"})
    assert charged.status_code == 200
    ticket = charged.json()
    assert ticket["movement_id"]
    assert ticket["order_id"] == tab_id
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == 3
    assert shop.store.get_order(PILOT_TENANT_ID, UUID(tab_id)).status == "placed"
    session = client.get("/api/cash/session").json()["session"]
    assert session["in"] == ticket["total"]
