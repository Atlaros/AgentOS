"""T9 Contabilidad: COGS from weighted-avg purchase cost (ADR-011 Fase 3)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from factory_os.domain.journal import assert_journal_balanced, sum_by_direction
from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"


def _codes(lines) -> dict[str, str]:
    return {line.direction: (line.account_code or "") for line in lines}


def test_purchase_then_cash_sale_posts_cogs() -> None:
    shop = make_shop()
    client = owner_client(shop)
    received = client.post(
        "/api/stock/receive",
        json={"variant_sku": SKU, "quantity": 2, "unit_cost": "20"},
    )
    assert received.status_code == 200

    client.post("/api/cash/session/open", json={"opening_float": "0"})
    sold = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert sold.status_code == 200
    sale_id = UUID(sold.json()["id"])

    entry = shop.store.get_journal_by_origin(PILOT_TENANT_ID, "cogs", sale_id, "post")
    assert entry is not None
    assert_journal_balanced(entry.lines)
    by_dir = _codes(entry.lines)
    assert by_dir["debit"] == "5110"
    assert by_dir["credit"] == "1300"
    assert sum_by_direction(entry.lines, "debit") == Decimal("20.00")


def test_void_cash_sale_reverses_cogs() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post(
        "/api/stock/receive",
        json={"variant_sku": SKU, "quantity": 1, "unit_cost": "12"},
    )
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    sold = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert sold.status_code == 200
    body = sold.json()
    sale_id = UUID(body["id"])
    movement_id = body.get("movement_id")
    assert movement_id

    voided = client.post(f"/api/cash/{movement_id}/void", json={"reason": "cliente desistio"})
    assert voided.status_code == 200

    post = shop.store.get_journal_by_origin(PILOT_TENANT_ID, "cogs", sale_id, "post")
    reverse = shop.store.get_journal_by_origin(PILOT_TENANT_ID, "cogs", sale_id, "reverse")
    assert post is not None
    assert reverse is not None
    assert reverse.reverses_entry_id == post.id
    assert_journal_balanced(reverse.lines)


def test_sale_without_purchase_skips_cogs() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    sold = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert sold.status_code == 200
    sale_id = UUID(sold.json()["id"])

    entry = shop.store.get_journal_by_origin(PILOT_TENANT_ID, "cogs", sale_id, "post")
    assert entry is None
