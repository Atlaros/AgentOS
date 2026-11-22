"""ADR-015 Fase B: thumb_url / media_id on catalog, orders, replenishment."""

from __future__ import annotations

from pathlib import Path

from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def _upload_primary(client, tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    monkeypatch.setenv("CATALOG_IMAGES_DIR", str(tmp_path))
    res = client.post(
        f"/api/catalog/{SKU}/image",
        files={"file": ("one.png", PNG, "image/png")},
    )
    assert res.status_code == 200, res.text
    asset_id = res.json()["asset_id"]
    assert asset_id
    return asset_id


def test_catalog_list_exposes_media_thumb(tmp_path: Path, monkeypatch) -> None:
    shop = make_shop()
    client = owner_client(shop)
    asset_id = _upload_primary(client, tmp_path, monkeypatch)

    res = client.get("/api/catalog?limit=200")
    assert res.status_code == 200
    row = next(p for p in res.json()["products"] if p["variant_sku"] == SKU)
    assert row.get("media_id") == asset_id
    assert row.get("thumb_url", "").startswith("/api/media/")


def test_order_items_include_thumb_url(tmp_path: Path, monkeypatch) -> None:
    shop = make_shop()
    client = owner_client(shop)
    asset_id = _upload_primary(client, tmp_path, monkeypatch)

    created = client.post(
        "/api/orders",
        json={
            "wa_number": "59170000099",
            "name": "Thumb Test",
            "items": [{"variant_sku": SKU, "quantity": 1}],
        },
    )
    assert created.status_code == 200, created.text

    listed = client.get("/api/orders")
    assert listed.status_code == 200
    orders = listed.json()["orders"]
    assert orders
    item = next(
        line
        for order in orders
        for line in order["items"]
        if line["variant_sku"] == SKU
    )
    assert item.get("media_id") == asset_id
    assert item.get("thumb_url", "").startswith("/api/media/")


def test_replenishment_items_include_thumb_url(tmp_path: Path, monkeypatch) -> None:
    shop = make_shop()
    client = owner_client(shop)
    asset_id = _upload_primary(client, tmp_path, monkeypatch)

    record = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert record is not None
    record.stock = 0
    shop.store.upsert_variant(record)
    shop.store.set_reorder_threshold(PILOT_TENANT_ID, SKU, 2)

    res = client.get("/api/suppliers/replenishment")
    assert res.status_code == 200
    items = [item for group in res.json()["groups"] for item in group["items"]]
    hit = next(item for item in items if item["variant_sku"] == SKU)
    assert hit.get("media_id") == asset_id
    assert hit.get("thumb_url", "").startswith("/api/media/")


def test_cash_grid_service_selectable_with_zero_stock() -> None:
    shop = make_shop()
    client = owner_client(shop)
    created = client.post(
        "/api/catalog",
        json={
            "codigo": "corte-b",
            "name": "Corte B",
            "price": "40",
            "stock": 0,
            "category": "Servicios",
            "tracks_stock": False,
        },
    )
    assert created.status_code == 200, created.text
    grid = client.get("/api/cash/grid")
    assert grid.status_code == 200
    product = next(p for p in grid.json()["products"] if p["product_sku"] == "corte-b")
    assert product["sold_out"] is False
    variant = product["variants"][0]
    assert variant["selectable"] is True
    assert int(variant["stock"]) == 0
