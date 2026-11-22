"""T4 counter grid: product, variants, sold out, search. Price stays on the server."""

from __future__ import annotations

from decimal import Decimal

from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"


def _product(body: dict, sku: str) -> dict:
    for product in body["products"]:
        if any(item["variant_sku"] == sku for item in product["variants"]):
            return product
    raise AssertionError(sku)


def test_cash_grid_groups_variants_shows_sold_out_and_server_price() -> None:
    shop = make_shop()
    client = owner_client(shop)
    record = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert record is not None
    catalog_price = record.price
    product_sku = record.product_sku

    grid = client.get("/api/cash/grid")
    assert grid.status_code == 200
    product = _product(grid.json(), SKU)
    assert product["product_sku"] == product_sku
    assert len(product["variants"]) >= 1
    variant = next(item for item in product["variants"] if item["variant_sku"] == SKU)
    assert Decimal(variant["price"]) == catalog_price
    assert variant["selectable"] is True
    assert variant["sold_out"] is False
    assert all("pago1" not in item["variant_sku"] for product in grid.json()["products"] for item in product["variants"])

    client.post("/api/cash/session/open", json={"opening_float": "0"})
    sale = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU, "quantity": 1, "price": "1.00"}]},
    )
    assert sale.status_code == 200
    assert Decimal(sale.json()["lines"][0]["unit_price"]) == catalog_price

    again = client.get("/api/cash/grid", params={"q": "h001"})
    assert again.status_code == 200
    sold = _product(again.json(), SKU)
    sold_variant = next(item for item in sold["variants"] if item["variant_sku"] == SKU)
    assert sold_variant["sold_out"] is True
    assert sold_variant["selectable"] is False

    for item in shop.store.iter_variants():
        if item.product_sku == product_sku:
            item.category = "Bebidas"
    filtered = client.get("/api/cash/grid", params={"category": "Bebidas"})
    assert filtered.status_code == 200
    assert any(
        item["variant_sku"] == SKU
        for product in filtered.json()["products"]
        for item in product["variants"]
    )
    other = client.get("/api/cash/grid", params={"category": "Nadie"})
    assert other.status_code == 200
    assert other.json()["products"] == []
