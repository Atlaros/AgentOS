"""T11: one ticket discount, supervisor PIN, catalog price stays."""

from decimal import Decimal

from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client
from tests.test_caja_combo import _staff

SKU = "cafe"


def _stock(shop) -> int:
    return int(shop.store.get_variant(PILOT_TENANT_ID, SKU).stock)


def test_ticket_discount_uses_catalog_price_and_supervisor_pin() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    owner.post("/api/cash/session/open", json={"opening_float": "0"})
    created = owner.post(
        "/api/catalog",
        json={"codigo": SKU, "name": "Café", "price": "10", "stock": 5, "category": "Bebidas"},
    )
    assert created.status_code == 200, created.text
    owner.post(
        "/api/panel/users",
        json={"name": "Luis", "email": "luis@taller.local", "role": "staff", "secret": "staff-secret-1"},
    )
    owner.post(
        "/api/panel/users",
        json={
            "name": "Ana",
            "email": "ana@taller.local",
            "role": "supervisor",
            "secret": "super-secret-1",
            "pin": "2468",
        },
    )
    staff = _staff(shop, "staff-secret-1")
    supervisor = _staff(shop, "super-secret-1")
    line = {"variant_sku": SKU, "quantity": 1, "unit_price": "1.00"}

    plain = staff.post("/api/cash/sales", json={"method": "cash", "lines": [line]})
    assert plain.status_code == 200, plain.text
    assert Decimal(plain.json()["lines"][0]["unit_price"]) == Decimal("10.00")
    assert Decimal(plain.json()["total"]) == Decimal("10.00")
    assert _stock(shop) == 4

    denied = staff.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [line], "discount_amount": "2.50", "pin": "2468"},
    )
    assert denied.status_code == 403
    assert _stock(shop) == 4

    missing = supervisor.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [line], "discount_amount": "2.50"},
    )
    assert missing.status_code == 400
    assert missing.json()["detail"] == "pin_required"
    assert _stock(shop) == 4

    wrong = supervisor.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [line], "discount_amount": "2.50", "pin": "0000"},
    )
    assert wrong.status_code == 403
    assert _stock(shop) == 4

    over = supervisor.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [line], "discount_amount": "10.01", "pin": "2468"},
    )
    assert over.status_code == 400
    assert over.json()["detail"] == "discount_exceeds"
    assert _stock(shop) == 4

    sale = supervisor.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [line], "discount_amount": "2.50", "pin": "2468"},
    )
    assert sale.status_code == 200, sale.text
    body = sale.json()
    assert Decimal(body["lines"][0]["unit_price"]) == Decimal("10.00")
    assert Decimal(body["discount_amount"]) == Decimal("2.50")
    assert Decimal(body["total"]) == Decimal("7.50")
    assert _stock(shop) == 3
    order = shop.store.get_order(PILOT_TENANT_ID, shop.store.list_orders(PILOT_TENANT_ID)[-1].id)
    assert order is not None
    assert order.discount_amount == Decimal("2.50")
