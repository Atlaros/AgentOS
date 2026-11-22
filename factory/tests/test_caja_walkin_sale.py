"""T3 walk-in cash sale: ticket plus a counter order (ADR-009 amendment)."""

from __future__ import annotations

from decimal import Decimal

from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"


def test_walkin_search_and_cash_sale_creates_ticket_and_counter_order() -> None:
    shop = make_shop()
    client = owner_client(shop)
    orders_before = len(shop.store.list_orders(PILOT_TENANT_ID))

    client.post("/api/cash/session/open", json={"opening_float": "0"})

    by_code = client.get("/api/cash/catalog", params={"q": "h001"})
    assert by_code.status_code == 200
    hits = by_code.json()["hits"]
    assert any(hit["variant_sku"] == SKU for hit in hits)
    hit = next(h for h in hits if h["variant_sku"] == SKU)
    assert "price" in hit
    assert Decimal(str(hit["price"])) > 0

    by_price = client.get("/api/cash/catalog", params={"q": str(hit["price"])})
    assert by_price.status_code == 200
    assert any(h["variant_sku"] == SKU for h in by_price.json()["hits"])

    by_name = client.get("/api/cash/catalog", params={"q": "blusa"})
    assert by_name.status_code == 200
    assert any(h["variant_sku"] == SKU for h in by_name.json()["hits"])

    sale = client.post(
        "/api/cash/sales",
        json={
            "method": "cash",
            "lines": [{"variant_sku": SKU, "quantity": 1}],
        },
    )
    assert sale.status_code == 200
    ticket = sale.json()
    assert ticket["status"] == "recorded"
    assert ticket["method"] == "cash"
    assert ticket["number"].startswith("TK-")
    assert ticket["total"]
    assert len(ticket["lines"]) == 1
    assert ticket["lines"][0]["variant_sku"] == SKU
    assert ticket["movement_id"]
    assert ticket["created_at"]
    assert ticket.get("order_id")
    orders = shop.store.list_orders(PILOT_TENANT_ID)
    assert len(orders) == orders_before + 1
    order = next(item for item in orders if str(item.id) == ticket["order_id"])
    assert order.origin == "counter"
    assert order.status == "placed"

    variant = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert variant is not None
    assert variant.stock == 0
    assert variant.attributes.get("disabled") is True

    book = client.get("/api/cash").json()
    assert any(m["id"] == ticket["movement_id"] for m in book["movements"])
    mov = next(m for m in book["movements"] if m["id"] == ticket["movement_id"])
    assert mov["direction"] == "in"
    assert mov["category"] == "venta"
    assert mov["method"] == "cash"
    assert mov["ticket_id"] == ticket["id"]
    assert book["session"]["in"] == ticket["total"] or Decimal(book["session"]["in"]) == Decimal(
        ticket["total"]
    )

    fetched = client.get(f"/api/cash/sales/{ticket['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["number"] == ticket["number"]

    again = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert again.status_code == 409
    assert again.json()["detail"] in {"out_of_stock", "disabled_variant"}


def test_walkin_sale_requires_open_session() -> None:
    shop = make_shop()
    client = owner_client(shop)
    blocked = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "session_required"


def test_walkin_multi_line_cash_sale_creates_ticket_and_counter_order() -> None:
    """POS ticket: two SKUs on one ticket and one counter order."""
    shop = make_shop()
    client = owner_client(shop)
    orders_before = len(shop.store.list_orders(PILOT_TENANT_ID))
    sku_a = "h001-M-VP"
    sku_b = "h002-M-B"

    client.post("/api/cash/session/open", json={"opening_float": "0"})

    for sku in (sku_a, sku_b):
        variant = shop.store.get_variant(PILOT_TENANT_ID, sku)
        assert variant is not None
        assert variant.stock >= 1
        assert not variant.attributes.get("disabled")

    sale = client.post(
        "/api/cash/sales",
        json={
            "method": "cash",
            "lines": [
                {"variant_sku": sku_a, "quantity": 1},
                {"variant_sku": sku_b, "quantity": 1},
            ],
        },
    )
    assert sale.status_code == 200
    ticket = sale.json()
    assert ticket["status"] == "recorded"
    assert ticket["method"] == "cash"
    assert ticket["number"].startswith("TK-")
    assert ticket.get("order_id")
    orders = shop.store.list_orders(PILOT_TENANT_ID)
    assert len(orders) == orders_before + 1
    order = next(item for item in orders if str(item.id) == ticket["order_id"])
    assert order.origin == "counter"
    assert len(order.items) == 2

    line_skus = {line["variant_sku"] for line in ticket["lines"]}
    assert line_skus == {sku_a, sku_b}
    assert len(ticket["lines"]) == 2
    expected_total = sum(
        (Decimal(str(line["unit_price"])) * int(line["quantity"]) for line in ticket["lines"]),
        Decimal("0"),
    ).quantize(Decimal("0.01"))
    assert Decimal(str(ticket["total"])) == expected_total

    for sku in (sku_a, sku_b):
        variant = shop.store.get_variant(PILOT_TENANT_ID, sku)
        assert variant is not None
        assert variant.stock == 0
        assert variant.attributes.get("disabled") is True

    book = client.get("/api/cash").json()
    mov = next(m for m in book["movements"] if m["id"] == ticket["movement_id"])
    assert mov["category"] == "venta"
    assert mov["ticket_id"] == ticket["id"]


def test_walkin_sale_decrements_quantity_and_disables_only_at_zero() -> None:
    """Selling 2 of stock 5 leaves 3. Selling the rest disables the variant."""
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    shop.store.set_variant_availability(PILOT_TENANT_ID, SKU, available=True, stock=5)

    sale = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU, "quantity": 2}]},
    )
    assert sale.status_code == 200
    variant = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert variant is not None
    assert variant.stock == 3
    assert not variant.attributes.get("disabled")

    rest = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU, "quantity": 3}]},
    )
    assert rest.status_code == 200
    variant = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert variant is not None
    assert variant.stock == 0
    assert variant.attributes.get("disabled") is True
