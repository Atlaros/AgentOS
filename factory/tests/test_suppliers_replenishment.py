"""T3 ADR-012: replenishment grouped by supplier + draft purchase orders."""

from __future__ import annotations

from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.purchase_orders import suggested_qty
from factory_os.domain.replenishment import build_replenishment
from factory_os.domain.seed import load_pilot_catalog
from factory_os.domain.store import MemoryCommerceStore
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"


def _store() -> MemoryCommerceStore:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_pilot_catalog(store)
    return store


def test_low_stock_variant_appears_under_supplier_group() -> None:
    store = _store()
    supplier = store.create_supplier(PILOT_TENANT_ID, name="Textiles Andinos")
    store.set_variant_supplier(PILOT_TENANT_ID, SKU, supplier.id)
    store.set_reorder_threshold(PILOT_TENANT_ID, SKU, 5)
    record = store.get_variant(PILOT_TENANT_ID, SKU)
    assert record is not None
    record.stock = 2
    store.upsert_variant(record)

    payload = build_replenishment(store, PILOT_TENANT_ID)
    groups = payload["groups"]
    matched = next(g for g in groups if g.get("supplier_id") == str(supplier.id))
    skus = [item["variant_sku"] for item in matched["items"]]
    assert SKU in skus
    row = next(item for item in matched["items"] if item["variant_sku"] == SKU)
    deficit = max(0, int(row["reorder_threshold"]) - int(row["stock"]))
    assert int(row["suggested_qty"]) >= deficit
    assert int(row["suggested_qty"]) == suggested_qty(
        stock=int(row["stock"]),
        reorder_threshold=int(row["reorder_threshold"]),
        sold_proxy=int(row.get("sold_proxy") or row.get("ventas") or 0),
    )
    assert payload["cards"]["stock_bajo"] >= 1


def test_create_draft_po_listed_with_lines() -> None:
    shop = make_shop()
    client = owner_client(shop)
    supplier = shop.store.create_supplier(PILOT_TENANT_ID, name="Calzados Sur")
    created = client.post(
        "/api/purchase-orders",
        json={
            "supplier_id": str(supplier.id),
            "notes": "pedido piloto",
            "lines": [{"variant_sku": SKU, "quantity": 3, "unit_cost": "12.5"}],
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "draft"
    assert body["supplier_id"] == str(supplier.id)
    assert body["number"].startswith("PO-")
    assert len(body["lines"]) == 1
    assert body["lines"][0]["variant_sku"] == SKU
    assert body["lines"][0]["quantity_ordered"] == 3

    listed = client.get("/api/purchase-orders")
    assert listed.status_code == 200
    rows = listed.json()["purchase_orders"]
    assert any(row["id"] == body["id"] and row["status"] == "draft" for row in rows)

    detail = client.get(f"/api/purchase-orders/{body['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["lines"]) == 1
    assert detail.json()["lines"][0]["quantity_ordered"] == 3


def test_create_po_requires_supplier_and_lines() -> None:
    shop = make_shop()
    client = owner_client(shop)
    supplier = shop.store.create_supplier(PILOT_TENANT_ID, name="Sin Lineas")

    missing_supplier = client.post(
        "/api/purchase-orders",
        json={"lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert missing_supplier.status_code == 400

    empty_lines = client.post(
        "/api/purchase-orders",
        json={"supplier_id": str(supplier.id), "lines": []},
    )
    assert empty_lines.status_code == 400

    bad_qty = client.post(
        "/api/purchase-orders",
        json={"supplier_id": str(supplier.id), "lines": [{"variant_sku": SKU, "quantity": 0}]},
    )
    assert bad_qty.status_code == 400


def test_suggested_qty_covers_deficit() -> None:
    assert suggested_qty(stock=0, reorder_threshold=5, sold_proxy=0) >= 5
    assert suggested_qty(stock=3, reorder_threshold=5, sold_proxy=10) >= 2
    assert suggested_qty(stock=5, reorder_threshold=5, sold_proxy=0) >= 1


def test_api_replenishment_groups_and_cards() -> None:
    shop = make_shop()
    client = owner_client(shop)
    supplier = shop.store.create_supplier(PILOT_TENANT_ID, name="API Grupo")
    shop.store.set_variant_supplier(PILOT_TENANT_ID, SKU, supplier.id)
    shop.store.set_reorder_threshold(PILOT_TENANT_ID, SKU, 8)
    record = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert record is not None
    record.stock = 0
    shop.store.upsert_variant(record)

    res = client.get("/api/suppliers/replenishment")
    assert res.status_code == 200
    body = res.json()
    assert "groups" in body
    assert "cards" in body
    assert body["cards"]["sin_stock"] >= 1
    group = next(g for g in body["groups"] if g.get("supplier_id") == str(supplier.id))
    assert any(item["variant_sku"] == SKU for item in group["items"])
