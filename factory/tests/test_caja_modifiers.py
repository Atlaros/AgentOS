"""T9: a catalog modifier is chosen on the line. The server adds its price."""

from decimal import Decimal
from uuid import uuid4

from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client
from tests.test_caja_combo import _staff

SKU = "pago1-U-B"


def test_modifier_price_comes_from_the_server_and_stock_follows_quantity() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    opening = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert opening is not None
    opening_stock = int(opening.stock)
    created = client.post(
        "/api/catalog/modifiers",
        json={"name": "Extra", "price_delta": "3.50"},
    )
    assert created.status_code == 200, created.text
    modifier_id = created.json()["id"]
    sale = client.post(
        "/api/cash/sales",
        json={
            "method": "cash",
            "lines": [
                {
                    "variant_sku": SKU,
                    "quantity": 2,
                    "options": [modifier_id],
                    "unit_price": "0.01",
                }
            ],
        },
    )
    assert sale.status_code == 200, sale.text
    line = sale.json()["lines"][0]
    unit = (Decimal(opening.price) + Decimal("3.50")).quantize(Decimal("0.01"))
    assert Decimal(line["unit_price"]) == unit
    assert Decimal(sale.json()["total"]) == (unit * 2).quantize(Decimal("0.01"))
    assert line["options"][0]["name"] == "Extra"
    assert line["options"][0]["price_delta"] == "3.50"
    order = shop.store.get_order(PILOT_TENANT_ID, shop.store.list_orders(PILOT_TENANT_ID)[-1].id)
    assert order is not None
    assert order.items[0].options[0]["name"] == "Extra"
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == opening_stock - 2


def test_unknown_modifier_does_not_sell() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    opening = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    sale = client.post(
        "/api/cash/sales",
        json={
            "method": "cash",
            "lines": [{"variant_sku": SKU, "quantity": 1, "options": [str(uuid4())]}],
        },
    )
    assert sale.status_code == 400
    assert sale.json()["detail"] == "unknown_modifier"
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == opening.stock


def test_same_sku_with_different_options_stays_two_lines() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    extra = client.post("/api/catalog/modifiers", json={"name": "Extra", "price_delta": "1.00"})
    assert extra.status_code == 200, extra.text
    modifier_id = extra.json()["id"]
    opening = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert opening is not None
    opening_stock = int(opening.stock)
    sale = client.post(
        "/api/cash/sales",
        json={
            "method": "cash",
            "lines": [
                {"variant_sku": SKU, "quantity": 1, "options": []},
                {"variant_sku": SKU, "quantity": 1, "options": [modifier_id]},
            ],
        },
    )
    assert sale.status_code == 200, sale.text
    lines = sale.json()["lines"]
    assert len(lines) == 2
    assert lines[0].get("options") in (None, [])
    assert lines[1]["options"][0]["id"] == modifier_id
    plain = Decimal(opening.price).quantize(Decimal("0.01"))
    assert Decimal(lines[0]["unit_price"]) == plain
    assert Decimal(lines[1]["unit_price"]) == (plain + Decimal("1.00")).quantize(Decimal("0.01"))
    assert shop.store.get_variant(PILOT_TENANT_ID, SKU).stock == opening_stock - 2


def test_staff_cannot_define_a_modifier() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    created = owner.post(
        "/api/panel/users",
        json={"name": "Luis", "email": "luis@taller.local", "role": "staff", "secret": "staff-secret-1"},
    )
    assert created.status_code == 200
    staff = _staff(shop, "staff-secret-1")
    denied = staff.post("/api/catalog/modifiers", json={"name": "Extra", "price_delta": "1"})
    assert denied.status_code == 403
    listed = owner.get("/api/catalog/modifiers")
    assert listed.status_code == 200
    assert listed.json()["modifiers"] == []
