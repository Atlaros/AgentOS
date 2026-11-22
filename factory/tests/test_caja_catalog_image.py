"""T3 catalog photo paths and category order (ADR-009 amendment)."""

from __future__ import annotations

from pathlib import Path

from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def test_product_image_is_a_file_path_and_sale_works_without_one(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CATALOG_IMAGES_DIR", str(tmp_path))
    shop = make_shop()
    client = owner_client(shop)
    upload = client.post(
        f"/api/catalog/{SKU}/image",
        files={"file": ("cafe.png", PNG, "image/png")},
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["image_path"]
    assert body["thumb_path"]
    assert body["image_path"] != body["thumb_path"]
    assert PNG not in str(body).encode()
    original = tmp_path.joinpath(*Path(body["image_path"]).parts)
    thumb = tmp_path.joinpath(*Path(body["thumb_path"]).parts)
    assert original.read_bytes() == PNG
    assert thumb.is_file()
    assert thumb.stat().st_size < 2 * 1024 * 1024
    record = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert record is not None
    assert record.attributes["image_path"] == body["image_path"]
    assert "image_url" not in record.attributes or not str(record.attributes["image_url"]).startswith(
        "\\x"
    )

    record.attributes.pop("image_path", None)
    record.attributes.pop("thumb_path", None)
    record.attributes.pop("image_url", None)
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    sale = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert sale.status_code == 200


def test_categories_follow_sort_order_and_blank_is_uncategorized() -> None:
    shop = make_shop()
    client = owner_client(shop)
    drinks = shop.store.get_variant(PILOT_TENANT_ID, "h001-M-VP")
    food = shop.store.get_variant(PILOT_TENANT_ID, "h002-M-B")
    assert drinks is not None and food is not None
    drinks.category = "Bebidas"
    food.category = "Comidas"
    blank = shop.store.get_variant(PILOT_TENANT_ID, "pago1-U-B")
    assert blank is not None
    blank.category = ""

    ordered = client.patch(
        "/api/catalog/categories",
        json={"name": "Comidas", "sort_order": 1},
    )
    assert ordered.status_code == 200
    assert client.patch(
        "/api/catalog/categories", json={"name": "Bebidas", "sort_order": 2}
    ).status_code == 200
    names = [row["name"] for row in client.get("/api/catalog/categories").json()["categories"]]
    assert names.index("Comidas") < names.index("Bebidas")
    assert "Sin categoría" in names
