"""Cafeteria pilot seed (ADR-016). Pytest Closet stays on load_pilot_catalog."""

from __future__ import annotations

import json
from decimal import Decimal

from factory_os.domain.knowledge import load_shop_pack
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.seed import catalog_seed_path, extra_seed_paths, load_catalog_json
from factory_os.domain.store import MemoryCommerceStore


def test_cafe_catalog_has_owner_prices() -> None:
    payload = json.loads(catalog_seed_path("cafe").read_text(encoding="utf-8"))
    products = payload["products"]
    assert payload["tenant_id"] == str(PILOT_TENANT_ID)
    assert len(products) == 53
    assert [row["sku"] for row in products] == [
        f"c{index:03d}" for index in range(1, 55) if index != 48
    ]
    assert extra_seed_paths("cafe") == []
    by_name = {row["name"]: row for row in products}
    assert Decimal(by_name["Café con leche 200ml"]["amount"]) == Decimal("3.00")
    assert Decimal(by_name["Café con leche 400ml"]["amount"]) == Decimal("6.00")
    assert Decimal(by_name["Café 200ml"]["amount"]) == Decimal("2.00")
    assert Decimal(by_name["Café 400ml"]["amount"]) == Decimal("4.00")
    shared_with_closet = [f"c{index:03d}" for index in range(1, 6)]
    by_sku = {row["sku"]: row for row in products}
    assert all(by_sku[sku]["variant_sku"] == sku for sku in shared_with_closet)
    for row in products:
        assert row["variant_sku"] == row["sku"]
        assert row["currency"] == "BOB"
        assert row["available_quantity"] == 100
        assert row["low_stock_threshold"] == 10
        attrs = row["attributes"]
        assert attrs["codigo"] == row["sku"]
        assert attrs["tracks_stock"] is True
        assert attrs["category"]


def test_cafe_catalog_loads_without_closet_overlay() -> None:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(catalog_seed_path("cafe"), store)
    assert len(store.variants) == 53
    assert "h001" not in {record.product_sku for record in store.variants.values()}


def test_cafe_shop_pack_follows_catalog_seed(monkeypatch) -> None:
    monkeypatch.setenv("CATALOG_SEED", "cafe")
    load_shop_pack.cache_clear()
    try:
        pack = load_shop_pack()
    finally:
        load_shop_pack.cache_clear()
    assert pack["profile"]["name"] == "Del Campus Café"
    assert pack["vocabulary"]["item"] == "producto"
    assert pack["policies"]["payment_window_min"] == 15
    assert pack["policies"]["pickup"] is True
    assert pack["policies"]["delivery"] is True
    assert pack["voice"]["address"] == "usted"
    assert "Venezuela" in str(pack["profile"].get("address") or "")
    blob = json.dumps(pack, ensure_ascii=False).lower()
    assert "tiktok" not in blob
    assert "instagram" not in blob
    assert "el chat no confirma el pago" in blob or "mensaje del cliente no confirma" in blob


def test_unknown_catalog_seed_fails_closed() -> None:
    import pytest

    with pytest.raises(FileNotFoundError, match="unknown catalog seed"):
        catalog_seed_path("not-a-seed")
