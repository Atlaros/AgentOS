"""T2 ADR-012: rich direct stock receive (cost, supplier, cash/credit)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from factory_os.domain.journal import assert_journal_balanced, sum_by_direction
from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"


def _codes(lines) -> dict[str, str]:
    return {line.direction: (line.account_code or "") for line in lines}


def test_receive_credit_with_supplier_posts_cxp() -> None:
    shop = make_shop()
    client = owner_client(shop)
    supplier = shop.store.create_supplier(PILOT_TENANT_ID, name="Textiles Andinos")

    before = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert before is not None
    stock_before = before.stock

    received = client.post(
        "/api/stock/receive",
        json={
            "variant_sku": SKU,
            "quantity": 2,
            "unit_cost": "15",
            "supplier_id": str(supplier.id),
            "payment_method": "credit",
        },
    )
    assert received.status_code == 200
    body = received.json()
    assert body["received"] == 2
    assert body["stock"] == stock_before + 2
    assert body["payment_method"] == "credit"
    assert body["supplier_id"] == str(supplier.id)
    receipt_id = UUID(body["purchase_id"])

    purchases = shop.store.list_purchases(PILOT_TENANT_ID)
    receipt = next(item for item in purchases if item.id == receipt_id)
    assert receipt.payment_method == "credit"
    assert receipt.supplier_id == supplier.id
    assert receipt.unit_cost == Decimal("15")

    entry = shop.store.get_journal_by_origin(PILOT_TENANT_ID, "purchase", receipt_id, "post")
    assert entry is not None
    assert_journal_balanced(entry.lines)
    by_dir = _codes(entry.lines)
    assert by_dir["debit"] == "1300"
    assert by_dir["credit"] == "2100"
    assert sum_by_direction(entry.lines, "debit") == Decimal("30.00")


def test_receive_cash_posts_inventario_caja() -> None:
    shop = make_shop()
    client = owner_client(shop)
    received = client.post(
        "/api/stock/receive",
        json={
            "variant_sku": SKU,
            "quantity": 1,
            "unit_cost": "20",
            "payment_method": "cash",
        },
    )
    assert received.status_code == 200
    receipt_id = UUID(received.json()["purchase_id"])
    assert received.json()["payment_method"] == "cash"

    entry = shop.store.get_journal_by_origin(PILOT_TENANT_ID, "purchase", receipt_id, "post")
    assert entry is not None
    assert_journal_balanced(entry.lines)
    by_dir = _codes(entry.lines)
    assert by_dir["debit"] == "1300"
    assert by_dir["credit"] == "1100"
    assert sum_by_direction(entry.lines, "debit") == Decimal("20.00")


def test_receive_without_unit_cost_returns_400() -> None:
    shop = make_shop()
    client = owner_client(shop)
    missing = client.post(
        "/api/stock/receive",
        json={"variant_sku": SKU, "quantity": 1},
    )
    assert missing.status_code == 400
    assert missing.json()["detail"] in {"bad_purchase", "unit_cost_required", "bad_receive"}


def test_low_stock_clears_after_receive_raises_stock() -> None:
    shop = make_shop()
    client = owner_client(shop)
    shop.store.set_reorder_threshold(PILOT_TENANT_ID, SKU, 50)
    record = shop.store.get_variant(PILOT_TENANT_ID, SKU)
    assert record is not None
    record.stock = 1
    shop.store.upsert_variant(record)

    low_before = client.get("/api/stock/low")
    assert low_before.status_code == 200
    assert any(item["variant_sku"] == SKU for item in low_before.json()["low_stock"])

    received = client.post(
        "/api/stock/receive",
        json={"variant_sku": SKU, "quantity": 60, "unit_cost": "12"},
    )
    assert received.status_code == 200
    assert received.json()["stock"] >= 50

    low_after = client.get("/api/stock/low")
    assert low_after.status_code == 200
    assert all(item["variant_sku"] != SKU for item in low_after.json()["low_stock"])
