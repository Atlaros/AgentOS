"""T10: Más vendidos is ranked from sold units. Price and stock stay put."""

from decimal import Decimal
from uuid import UUID

from factory_os.contracts.employees import EmployeeRole, identity_for
from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client

BEST = "Más vendidos"


def _add(client, codigo: str, name: str, price: str, stock: int) -> str:
    created = client.post(
        "/api/catalog",
        json={
            "codigo": codigo,
            "name": name,
            "price": price,
            "stock": stock,
            "category": "Bebidas",
        },
    )
    assert created.status_code == 200, created.text
    return created.json()["variant_sku"]


def test_bestsellers_rank_tickets_and_confirmed_chat_orders() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    cafe = _add(client, "cafe", "Café", "8", 10)
    pan = _add(client, "pan", "Pan", "4", 10)
    jugo = _add(client, "jugo", "Jugo", "6", 10)
    cafe_price = shop.store.get_variant(PILOT_TENANT_ID, cafe).price
    pan_price = shop.store.get_variant(PILOT_TENANT_ID, pan).price

    sale = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": cafe, "quantity": 1, "unit_price": "1"}]},
    )
    assert sale.status_code == 200, sale.text

    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59170004444")
    cobros = identity_for(EmployeeRole.COBROS, PILOT_TENANT_ID)
    confirmed = shop.tools.execute(
        cobros,
        "payment.create_qr",
        {"customer_id": str(customer.id), "variant_sku": pan, "quantity": 2},
        channel="whatsapp",
    )
    assert confirmed.get("error") is None, confirmed
    shop.store.confirm_from_adapter(confirmed["provider_ref"])
    waiting = shop.tools.execute(
        cobros,
        "payment.create_qr",
        {"customer_id": str(customer.id), "variant_sku": jugo, "quantity": 2},
        channel="whatsapp",
    )
    assert waiting.get("error") is None, waiting
    tab = client.post(
        "/api/cash/tabs",
        json={"table": "Mesa 2", "lines": [{"variant_sku": pan, "quantity": 1}]},
    )
    assert tab.status_code == 200, tab.text

    ranked = client.get("/api/cash/grid", params={"category": BEST})
    assert ranked.status_code == 200, ranked.text
    products = ranked.json()["products"]
    assert [item["product_sku"] for item in products[:2]] == [pan, cafe]
    assert all(item["product_sku"] != jugo for item in products)
    pan_card = products[0]
    cafe_card = products[1]
    assert pan_card["sold_units"] == 2
    assert cafe_card["sold_units"] == 1
    assert Decimal(pan_card["price"]) == Decimal(pan_price).quantize(Decimal("0.01"))
    assert Decimal(cafe_card["price"]) == Decimal(cafe_price).quantize(Decimal("0.01"))
    assert shop.store.get_variant(PILOT_TENANT_ID, pan).stock == 7
    assert shop.store.get_variant(PILOT_TENANT_ID, cafe).stock == 9
    assert shop.store.get_order(PILOT_TENANT_ID, UUID(waiting["order_id"])).status == "reserved"
