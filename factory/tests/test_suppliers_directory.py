"""T1 ADR-012: supplier directory, variant link, per-variant reorder threshold."""

from __future__ import annotations

import pytest

from factory_os.domain.models import PILOT_TENANT_ID, Supplier
from factory_os.domain.seed import load_pilot_catalog
from factory_os.domain.store import MemoryCommerceStore
from factory_os.domain.suppliers import list_low_stock


def _store() -> MemoryCommerceStore:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_pilot_catalog(store)
    return store


def test_create_supplier_appears_in_list() -> None:
    store = _store()
    created = store.create_supplier(PILOT_TENANT_ID, name="Textiles Andinos", phone="70000000")
    assert isinstance(created, Supplier)
    assert created.name == "Textiles Andinos"
    assert created.active is True

    listed = store.list_suppliers(PILOT_TENANT_ID, active_only=True)
    assert any(item.id == created.id for item in listed)
    fetched = store.get_supplier(PILOT_TENANT_ID, created.id)
    assert fetched is not None
    assert fetched.phone == "70000000"


def test_deactivate_hides_from_active_only_list() -> None:
    store = _store()
    created = store.create_supplier(PILOT_TENANT_ID, name="Proveedor Temporal")
    store.deactivate_supplier(PILOT_TENANT_ID, created.id)

    active = store.list_suppliers(PILOT_TENANT_ID, active_only=True)
    assert all(item.id != created.id for item in active)

    all_rows = store.list_suppliers(PILOT_TENANT_ID, active_only=False)
    found = next(item for item in all_rows if item.id == created.id)
    assert found.active is False


def test_variant_supplier_and_reorder_threshold_drive_low_stock() -> None:
    store = _store()
    supplier = store.create_supplier(PILOT_TENANT_ID, name="Calzados Sur")
    sku = "h001-M-VP"
    store.set_variant_supplier(PILOT_TENANT_ID, sku, supplier.id)
    store.set_reorder_threshold(PILOT_TENANT_ID, sku, 5)

    record = store.get_variant(PILOT_TENANT_ID, sku)
    assert record is not None
    assert record.supplier_id == supplier.id
    assert record.reorder_threshold == 5

    record.stock = 3
    store.upsert_variant(record)
    low = list_low_stock(store)
    assert any(item.variant_sku == sku for item in low)

    record.stock = 6
    store.upsert_variant(record)
    low_after = list_low_stock(store)
    assert all(item.variant_sku != sku for item in low_after)


def test_supplier_has_no_hard_delete() -> None:
    store = _store()
    assert not hasattr(store, "delete_supplier")
    created = store.create_supplier(PILOT_TENANT_ID, name="No Borrar")
    store.deactivate_supplier(PILOT_TENANT_ID, created.id)
    still = store.get_supplier(PILOT_TENANT_ID, created.id)
    assert still is not None
    assert still.active is False


def test_set_reorder_threshold_rejects_negative() -> None:
    store = _store()
    with pytest.raises(ValueError, match="bad_threshold"):
        store.set_reorder_threshold(PILOT_TENANT_ID, "h001-M-VP", -1)


def test_api_suppliers_crud_and_variant_link() -> None:
    from tests.conftest import make_shop, owner_client

    client = owner_client(make_shop())
    created = client.post(
        "/api/suppliers",
        json={"name": "API Proveedor", "whatsapp": "77112233", "payment_terms": "credit"},
    )
    assert created.status_code == 200
    body = created.json()
    supplier_id = body["id"]
    assert body["name"] == "API Proveedor"

    listed = client.get("/api/suppliers")
    assert listed.status_code == 200
    assert any(row["id"] == supplier_id for row in listed.json()["suppliers"])

    patched = client.patch(f"/api/suppliers/{supplier_id}", json={"contact_name": "Ana", "active": False})
    assert patched.status_code == 200
    assert patched.json()["contact_name"] == "Ana"
    assert patched.json()["active"] is False

    active_only = client.get("/api/suppliers")
    assert all(row["id"] != supplier_id for row in active_only.json()["suppliers"])
    all_rows = client.get("/api/suppliers?active_only=false")
    assert any(row["id"] == supplier_id and row["active"] is False for row in all_rows.json()["suppliers"])

    link = client.patch(
        "/api/catalog/variants/h001-M-VP/supplier",
        json={"supplier_id": supplier_id},
    )
    assert link.status_code == 200
    assert link.json()["supplier_id"] == supplier_id

    threshold = client.patch(
        "/api/catalog/variants/h001-M-VP/reorder-threshold",
        json={"threshold": 5},
    )
    assert threshold.status_code == 200
    assert threshold.json()["reorder_threshold"] == 5

    # Force stock to 3 via receive/adjust path: set availability stock
    client.post(
        "/api/catalog/h001-M-VP/availability",
        json={"available": True, "stock": 3},
    )
    low = client.get("/api/stock/low").json()
    assert any(item["variant_sku"] == "h001-M-VP" for item in low["low_stock"])

    client.post(
        "/api/catalog/h001-M-VP/availability",
        json={"available": True, "stock": 6},
    )
    low_ok = client.get("/api/stock/low").json()
    assert all(item["variant_sku"] != "h001-M-VP" for item in low_ok["low_stock"])
