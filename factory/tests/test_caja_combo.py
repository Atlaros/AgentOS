"""T6 combos: no stock of their own. Selling one decrements each component."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient

from factory_os.api.main import create_app
from factory_os.domain.journal import sum_by_direction
from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import api_settings, make_shop, owner_client


def _staff(shop, secret: str) -> TestClient:
    client = TestClient(create_app(shop, api_settings()))
    client.headers["Authorization"] = f"Bearer {secret}"
    return client


def _components(client: TestClient) -> None:
    for codigo, name, stock in (("cafe", "Café", 4), ("pan", "Pan", 2)):
        created = client.post(
            "/api/catalog",
            json={
                "codigo": codigo,
                "name": name,
                "price": "8",
                "stock": stock,
                "category": "Bebidas",
            },
        )
        assert created.status_code == 200
        assert created.json()["variant_sku"] == codigo


def test_combo_sale_uses_components_and_catalog_price() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _components(client)
    created = client.post(
        "/api/catalog/combos",
        json={
            "codigo": "desayuno",
            "name": "Desayuno",
            "price": "18.00",
            "category": "Combos",
            "event_date": "2026-12-24",
            "components": [
                {"variant_sku": "cafe", "quantity": 1},
                {"variant_sku": "pan", "quantity": 1},
            ],
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["variant_sku"] == "desayuno"
    assert body["stock"] == 0
    assert body["event_date"] == "2026-12-24"
    assert Decimal(body["price"]) == Decimal("18.00")

    grid = client.get("/api/cash/grid", params={"q": "desayuno"})
    assert grid.status_code == 200
    product = grid.json()["products"][0]
    variant = product["variants"][0]
    assert variant["variant_sku"] == "desayuno"
    assert variant["stock"] == 2
    assert variant["selectable"] is True
    assert Decimal(variant["price"]) == Decimal("18.00")

    client.post("/api/cash/session/open", json={"opening_float": "0"})
    sale = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": "desayuno", "quantity": 1, "price": "1"}]},
    )
    assert sale.status_code == 200
    line = sale.json()["lines"][0]
    assert line["variant_sku"] == "desayuno"
    assert Decimal(line["unit_price"]) == Decimal("18.00")
    assert "options" not in line
    cafe = shop.store.get_variant(PILOT_TENANT_ID, "cafe")
    pan = shop.store.get_variant(PILOT_TENANT_ID, "pan")
    combo = shop.store.get_variant(PILOT_TENANT_ID, "desayuno")
    assert cafe is not None and cafe.stock == 3
    assert pan is not None and pan.stock == 1
    assert combo is not None and combo.stock == 0
    orders = [order for order in shop.store.list_orders(PILOT_TENANT_ID) if order.origin == "counter"]
    assert len(orders[-1].items) == 1
    assert orders[-1].items[0].variant_sku == "desayuno"

    sold_out = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": "desayuno", "quantity": 2}]},
    )
    assert sold_out.status_code == 409
    assert pan.stock == 1

    last = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": "desayuno", "quantity": 1}]},
    )
    assert last.status_code == 200
    again = client.get("/api/cash/grid", params={"q": "desayuno"})
    card = again.json()["products"][0]["variants"][0]
    assert card["sold_out"] is True
    assert card["selectable"] is False


def test_combo_price_requires_supervisor_pin() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    _components(owner)
    staff_user = owner.post(
        "/api/panel/users",
        json={"name": "Luis", "email": "luis@taller.local", "role": "staff", "secret": "staff-secret-1"},
    )
    assert staff_user.status_code == 200
    supervisor = owner.post(
        "/api/panel/users",
        json={
            "name": "Ana",
            "email": "ana@taller.local",
            "role": "supervisor",
            "secret": "super-secret-1",
            "pin": "2468",
        },
    )
    assert supervisor.status_code == 200
    payload = {
        "codigo": "desayuno",
        "name": "Desayuno",
        "price": "18.00",
        "components": [{"variant_sku": "cafe", "quantity": 1}, {"variant_sku": "pan", "quantity": 1}],
    }
    staff = _staff(shop, "staff-secret-1")
    assert staff.post("/api/catalog/combos", json=payload).status_code == 403
    super_client = _staff(shop, "super-secret-1")
    missing = super_client.post("/api/catalog/combos", json=payload)
    assert missing.status_code == 400
    assert missing.json()["detail"] == "pin_required"
    bad = super_client.post("/api/catalog/combos", json={**payload, "pin": "0000"})
    assert bad.status_code == 403
    created = super_client.post("/api/catalog/combos", json={**payload, "pin": "2468"})
    assert created.status_code == 200

    locked = owner.patch("/api/catalog/desayuno", json={"price": "1.00"})
    assert locked.status_code == 409
    assert locked.json()["detail"] == "combo_price_locked"
    changed = super_client.patch(
        "/api/catalog/combos/desayuno",
        json={"price": "20.00", "pin": "2468"},
    )
    assert changed.status_code == 200
    assert Decimal(changed.json()["price"]) == Decimal("20.00")
    record = shop.store.get_variant(PILOT_TENANT_ID, "desayuno")
    assert record is not None
    assert record.price == Decimal("20.00")


def test_open_tab_holds_combo_components_once() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _components(client)
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
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    opened = client.post(
        "/api/cash/tabs",
        json={"table": "Mesa 2", "lines": [{"variant_sku": "desayuno", "quantity": 1}]},
    )
    assert opened.status_code == 200
    tab_id = opened.json()["id"]
    assert shop.store.get_variant(PILOT_TENANT_ID, "cafe").stock == 3
    assert shop.store.get_variant(PILOT_TENANT_ID, "pan").stock == 1
    cancelled = client.post(f"/api/cash/tabs/{tab_id}/cancel")
    assert cancelled.status_code == 200
    assert shop.store.get_variant(PILOT_TENANT_ID, "cafe").stock == 4
    assert shop.store.get_variant(PILOT_TENANT_ID, "pan").stock == 2

    again = client.post(
        "/api/cash/tabs",
        json={"table": "Mesa 2", "lines": [{"variant_sku": "desayuno", "quantity": 1}]},
    )
    charged = client.post(f"/api/cash/tabs/{again.json()['id']}/charge", json={"method": "cash"})
    assert charged.status_code == 200
    assert Decimal(charged.json()["total"]) == Decimal("18.00")
    assert shop.store.get_variant(PILOT_TENANT_ID, "cafe").stock == 3
    assert shop.store.get_variant(PILOT_TENANT_ID, "pan").stock == 1


def test_combo_cogs_uses_component_cost() -> None:
    shop = make_shop()
    client = owner_client(shop)
    for codigo, name in (("cafe", "Café"), ("pan", "Pan")):
        assert client.post(
            "/api/catalog",
            json={"codigo": codigo, "name": name, "price": "8", "stock": 0, "category": "Bebidas"},
        ).status_code == 200
    assert client.post(
        "/api/stock/receive", json={"variant_sku": "cafe", "quantity": 3, "unit_cost": "8"}
    ).status_code == 200
    assert client.post(
        "/api/stock/receive", json={"variant_sku": "pan", "quantity": 3, "unit_cost": "4"}
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
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    sale = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": "desayuno", "quantity": 1}]},
    )
    assert sale.status_code == 200
    entry = shop.store.get_journal_by_origin(PILOT_TENANT_ID, "cogs", UUID(sale.json()["id"]), "post")
    assert entry is not None
    assert sum_by_direction(entry.lines, "debit") == Decimal("12.00")
