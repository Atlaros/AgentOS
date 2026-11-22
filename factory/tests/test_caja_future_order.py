"""T7 future-day orders: the agent takes them. Today's stock stays put."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from factory_os.contracts.employees import EmployeeRole, identity_for
from factory_os.domain.future_orders import apply_due_future_orders
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.order_hold import release_expired_unpaid_orders
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"
WHEN = "2026-12-24"


def test_agent_future_order_does_not_take_todays_stock() -> None:
    shop = make_shop()
    client = owner_client(shop)
    opening = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert opening is not None and opening.stock == 1
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170000099")
    cobros = identity_for(EmployeeRole.COBROS, PILOT_TENANT_ID)

    created = shop.tools.execute(
        cobros,
        "payment.create_qr",
        {
            "customer_id": str(customer.id),
            "variant_sku": SKU,
            "quantity": 1,
            "fulfill_on": WHEN,
        },
        channel="whatsapp",
    )
    assert created.get("error") is None
    assert "No se restó el stock de hoy" in created["owner_notice"]
    assert WHEN in created["owner_notice"]
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == 1
    assert SKU not in shop.store.held_variant_skus(PILOT_TENANT_ID)

    order = shop.store.get_order(PILOT_TENANT_ID, UUID(created["order_id"]))
    assert order is not None
    assert order.origin == "agent"
    assert order.table_label == ""
    assert order.fulfill_on is not None
    assert order.fulfill_on.isoformat() == WHEN
    assert order.stock_applied is False

    listed = client.get("/api/orders")
    assert listed.status_code == 200
    row = next(item for item in listed.json()["orders"] if item["id"] == created["order_id"])
    assert row["fulfill_on"] == WHEN
    tabs = client.get("/api/cash/tabs")
    assert tabs.status_code == 200
    assert tabs.json()["tabs"] == []

    release_expired_unpaid_orders(
        shop.store, PILOT_TENANT_ID, now=datetime.now(UTC) + timedelta(hours=5)
    )
    assert shop.store.get_order(PILOT_TENANT_ID, order.id) is not None

    shop.store.confirm_from_adapter(created["provider_ref"])
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == 1

    client.post("/api/cash/session/open", json={"opening_float": "0"})
    sale = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert sale.status_code == 200
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == 0

    assert apply_due_future_orders(shop.store, PILOT_TENANT_ID, on=order.fulfill_on) == 0
    assert shop.store.get_order(PILOT_TENANT_ID, order.id).stock_applied is False

    shop.store.set_variant_availability(PILOT_TENANT_ID, SKU, available=True, stock=1)
    assert apply_due_future_orders(shop.store, PILOT_TENANT_ID, on=order.fulfill_on) == 1
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == 0
    assert shop.store.get_order(PILOT_TENANT_ID, order.id).stock_applied is True
    assert apply_due_future_orders(shop.store, PILOT_TENANT_ID, on=order.fulfill_on) == 0


def test_future_combo_consumes_components_on_its_day() -> None:
    shop = make_shop()
    client = owner_client(shop)
    for codigo, name in (("cafe", "Café"), ("pan", "Pan")):
        assert client.post(
            "/api/catalog",
            json={"codigo": codigo, "name": name, "price": "8", "stock": 3, "category": "Bebidas"},
        ).status_code == 200
    assert client.post(
        "/api/catalog/combos",
        json={
            "codigo": "desayuno",
            "name": "Desayuno",
            "price": "18",
            "components": [
                {"variant_sku": "cafe", "quantity": 1},
                {"variant_sku": "pan", "quantity": 1},
            ],
        },
    ).status_code == 200
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170000098")
    cobros = identity_for(EmployeeRole.COBROS, PILOT_TENANT_ID)
    created = shop.tools.execute(
        cobros,
        "payment.create_qr",
        {
            "customer_id": str(customer.id),
            "variant_sku": "desayuno",
            "quantity": 1,
            "fulfill_on": WHEN,
        },
        channel="whatsapp",
    )
    assert created.get("error") is None
    assert shop.store.get_variant(PILOT_TENANT_ID, "cafe").stock == 3
    order = shop.store.get_order(PILOT_TENANT_ID, UUID(created["order_id"]))
    assert apply_due_future_orders(shop.store, PILOT_TENANT_ID, on=order.fulfill_on) == 1
    assert shop.store.get_variant(PILOT_TENANT_ID, "cafe").stock == 2
    assert shop.store.get_variant(PILOT_TENANT_ID, "pan").stock == 2
    assert shop.store.get_variant(PILOT_TENANT_ID, "desayuno").stock == 0
