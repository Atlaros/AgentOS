"""T10–T11 Contabilidad: CxP, adjustments, balance sheet, bank recon (ADR-011 Fase 3)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from factory_os.domain.journal import assert_journal_balanced, sum_by_direction
from factory_os.domain.journal_reports import income_statement
from factory_os.domain.chart_accounts import ensure_chart_seed
from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"


def _codes(lines) -> dict[str, str]:
    return {line.direction: (line.account_code or "") for line in lines}


def test_credit_purchase_posts_inventario_cxp() -> None:
    shop = make_shop()
    client = owner_client(shop)
    received = client.post(
        "/api/stock/receive",
        json={
            "variant_sku": SKU,
            "quantity": 2,
            "unit_cost": "15",
            "payment_method": "credit",
        },
    )
    assert received.status_code == 200
    receipt_id = UUID(received.json()["purchase_id"])

    entry = shop.store.get_journal_by_origin(PILOT_TENANT_ID, "purchase", receipt_id, "post")
    assert entry is not None
    assert_journal_balanced(entry.lines)
    by_dir = _codes(entry.lines)
    assert by_dir["debit"] == "1300"
    assert by_dir["credit"] == "2100"
    assert sum_by_direction(entry.lines, "debit") == Decimal("30.00")


def test_manual_adjustment_api_posts_balanced_journal() -> None:
    shop = make_shop()
    client = owner_client(shop)
    posted = client.post(
        "/api/journal/adjustments",
        json={
            "memo": "ajuste inventario",
            "lines": [
                {"account_code": "1300", "direction": "debit", "amount": "10"},
                {"account_code": "5100", "direction": "credit", "amount": "10"},
            ],
        },
    )
    assert posted.status_code == 200
    body = posted.json()
    assert body["origin_source"] == "adjustment"
    assert body["kind"] == "post"
    entry_id = UUID(body["id"])
    entry = next(
        item for item in shop.store.list_journal_entries(PILOT_TENANT_ID) if item.id == entry_id
    )
    assert_journal_balanced(entry.lines)
    diario = client.get("/api/journal", params={"period": "month"})
    assert diario.status_code == 200
    ids = {row["id"] for row in diario.json()["entries"]}
    assert str(entry_id) in ids


def test_balance_sheet_and_bank_recon_apis() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": "100",
            "reason": "venta",
            "category": "venta",
            "method": "cash",
        },
    )

    balance = client.get("/api/journal/balance-sheet", params={"period": "month"})
    assert balance.status_code == 200
    body = balance.json()
    assert "assets" in body
    assert "liabilities" in body
    assert "equity" in body
    assert "balanced_check" in body
    assert "rows" in body

    recon = client.get("/api/journal/bank-recon", params={"period": "month"})
    assert recon.status_code == 200
    recon_body = recon.json()
    assert "bank_lines" in recon_body
    assert "payments" in recon_body
    assert "matches" in recon_body


def test_income_includes_cogs_when_cost_known() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post(
        "/api/stock/receive",
        json={"variant_sku": SKU, "quantity": 1, "unit_cost": "25"},
    )
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    sold = client.post(
        "/api/cash/sales",
        json={"method": "cash", "lines": [{"variant_sku": SKU, "quantity": 1}]},
    )
    assert sold.status_code == 200

    tenant = shop.store.tenant_id
    ensure_chart_seed(shop.store, tenant)
    stmt = income_statement(
        shop.store.list_journal_entries(tenant),
        shop.store.list_chart_accounts(tenant),
    )
    assert stmt["cogs"] == Decimal("25.00")
    assert stmt["result"] == stmt["revenue"] - stmt["cogs"] - stmt["expenses"] - stmt["draws"]
    assert "COGS" in stmt["note"] or "cogs" in stmt["note"].lower()

    api = client.get("/api/journal/income", params={"period": "month"})
    assert api.status_code == 200
    assert Decimal(api.json()["cogs"]) == Decimal("25.00")
