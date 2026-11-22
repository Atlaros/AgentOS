"""ADR-015 Fase A: media assets, authenticated serve, gallery."""

from __future__ import annotations

from pathlib import Path

from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def test_catalog_upload_creates_media_asset_and_serves_thumb(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    monkeypatch.setenv("CATALOG_IMAGES_DIR", str(tmp_path))
    shop = make_shop()
    client = owner_client(shop)

    first = client.post(
        f"/api/catalog/{SKU}/image",
        files={"file": ("one.png", PNG, "image/png")},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body.get("asset_id"), body
    assert body.get("thumb_url", "").startswith("/api/media/")
    asset_id = body["asset_id"]

    thumb = client.get(f"/api/media/{asset_id}?variant=thumb")
    assert thumb.status_code == 200
    assert thumb.headers.get("content-type", "").startswith("image/")
    assert len(thumb.content) > 0
    assert PNG not in thumb.content  # thumb is re-encoded jpeg

    from fastapi.testclient import TestClient
    from factory_os.api.main import create_app
    from tests.conftest import api_settings

    anon = TestClient(create_app(shop, api_settings()))
    assert anon.get(f"/api/media/{asset_id}?variant=thumb").status_code == 401

    second = client.post(
        f"/api/catalog/{SKU}/image",
        files={"file": ("two.png", PNG, "image/png")},
    )
    assert second.status_code == 200, second.text
    assert second.json()["asset_id"] != asset_id

    gallery = client.get(f"/api/catalog/{SKU}/media")
    assert gallery.status_code == 200, gallery.text
    items = gallery.json()["media"]
    assert len(items) == 2
    primaries = [row for row in items if row.get("is_primary")]
    assert len(primaries) == 1

    record = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert record is not None
    assert record.attributes.get("image_path") or record.attributes.get("media_id")

    grid = client.get("/api/cash/grid")
    assert grid.status_code == 200
    products = grid.json()["products"]
    h001 = next(row for row in products if row["product_sku"] == "h001")
    assert h001.get("media_id") == asset_id or h001.get("thumb_url", "").startswith("/api/media/")


def test_service_without_tracks_stock_does_not_decrement() -> None:
    shop = make_shop()
    client = owner_client(shop)
    created = client.post(
        "/api/catalog",
        json={
            "codigo": "corte",
            "name": "Corte",
            "price": "40",
            "stock": 0,
            "category": "Servicios",
            "tracks_stock": False,
        },
    )
    assert created.status_code == 200, created.text
    assert created.json().get("tracks_stock") is False
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    sale = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": "corte", "quantity": 1}]},
    )
    assert sale.status_code == 200, sale.text
    record = shop.store.get_variant(PILOT_TENANT_ID, "corte")
    assert record is not None
    assert int(record.stock) == 0
