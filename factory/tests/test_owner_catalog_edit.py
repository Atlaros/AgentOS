"""Owner catalog search and product edit."""

from __future__ import annotations

from decimal import Decimal

from tests.conftest import make_shop, owner_client

_SEARCH_FIELDS = (
    "name",
    "description",
    "category",
    "subcategory",
    "brand",
    "material",
    "codigo",
    "color",
    "talla",
    "variant_sku",
    "product_sku",
    "style",
    "season",
)


def _matches(row: dict, needle: str) -> bool:
    folded = needle.casefold()
    return any(folded in str(row.get(key) or "").casefold() for key in _SEARCH_FIELDS)


def test_catalog_q_filters_fields_and_empty_q_lists_all() -> None:
    shop = make_shop()
    client = owner_client(shop)
    added = client.post(
        "/api/catalog",
        json={
            "codigo": "zxsearch",
            "name": "Abrigo buscable",
            "price": "10",
            "stock": 1,
            "category": "cat-zxsearch",
            "subcategory": "sub-zxsearch",
            "brand": "marca-unica",
            "material": "lana-unica",
            "season": "temporada-unica",
            "style": "estilo-unico",
            "talla": "U",
            "color": "bermellon",
            "description": "descripcion-unica",
        },
    )
    assert added.status_code == 200
    sku = added.json()["variant_sku"]
    everything = client.get("/api/catalog?limit=200").json()["products"]
    assert len(everything) > 1
    assert any(row["variant_sku"] == sku for row in everything)

    for needle in (
        "abrigo buscable",
        "ABRIGO",
        "lana-unica",
        "BERMELLON",
        "zxsearch",
        "estilo-unico",
        "temporada-unica",
        "descripcion-unica",
        "marca-unica",
        "cat-zxsearch",
        "sub-zxsearch",
        sku,
    ):
        found = client.get("/api/catalog", params={"limit": 200, "q": needle}).json()["products"]
        assert found, needle
        assert all(_matches(row, needle) for row in found), needle
        assert any(row["variant_sku"] == sku for row in found), needle
        assert len(found) < len(everything)

    assert client.get("/api/catalog", params={"q": "nada-que-exista-qqq", "limit": 200}).json()["products"] == []
    empty = client.get("/api/catalog", params={"limit": 50, "q": "  "}).json()["products"]
    plain = client.get("/api/catalog", params={"limit": 50}).json()["products"]
    assert [row["variant_sku"] for row in empty] == [row["variant_sku"] for row in plain]


def test_catalog_patch_persists_name_stock_and_price() -> None:
    shop = make_shop()
    client = owner_client(shop)
    added = client.post(
        "/api/catalog",
        json={
            "codigo": "n901",
            "name": "Pollera nueva",
            "price": "80",
            "stock": 2,
            "category": "faldas",
            "material": "jean",
            "talla": "M",
            "color": "negro",
        },
    )
    assert added.status_code == 200
    sku = added.json()["variant_sku"]
    patched = client.patch(
        f"/api/catalog/{sku}",
        json={
            "name": "Pollera editada",
            "stock": 7,
            "price": "99.50",
            "talla": "XL",
            "codigo_referencia": "REF-901",
        },
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["name"] == "Pollera editada"
    assert body["stock"] == 7
    assert Decimal(body["price"]) == Decimal("99.50")
    assert body["variant_sku"] == sku
    assert body["product_sku"] == "n901"
    assert body["codigo"] == "n901"
    assert body["talla"] == "XL"
    assert body["codigo_referencia"] == "REF-901"
    assert body["material"] == "jean"
    listed = next(
        row for row in client.get("/api/catalog?limit=200").json()["products"] if row["variant_sku"] == sku
    )
    assert listed["name"] == "Pollera editada"
    assert listed["stock"] == 7
    assert Decimal(listed["price"]) == Decimal("99.50")
    assert listed["codigo"] == "n901"
    assert listed["variant_sku"] == sku
    assert listed["material"] == "jean"


def test_catalog_patch_rejects_negative_stock() -> None:
    shop = make_shop()
    client = owner_client(shop)
    added = client.post(
        "/api/catalog",
        json={"codigo": "n902", "name": "Blusa stock", "price": "40", "stock": 3},
    )
    sku = added.json()["variant_sku"]
    bad = client.patch(f"/api/catalog/{sku}", json={"stock": -1})
    assert bad.status_code == 400
    kept = next(
        row for row in client.get("/api/catalog?limit=200").json()["products"] if row["variant_sku"] == sku
    )
    assert kept["stock"] == 3
    assert kept["name"] == "Blusa stock"


def test_catalog_patch_missing_sku_is_404() -> None:
    client = owner_client(make_shop())
    missing = client.patch("/api/catalog/no-existe-sku", json={"name": "Nadie", "stock": 1})
    assert missing.status_code == 404
