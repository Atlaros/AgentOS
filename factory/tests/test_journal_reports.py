"""T5/T6 Contabilidad: mayor, trial balance, income statement (ADR-011 Fase 2)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from factory_os.domain.chart_accounts import ensure_chart_seed
from factory_os.domain.journal_reports import general_ledger, income_statement, trial_balance
from factory_os.domain.models import Payment, PaymentStatus
from tests.conftest import make_shop, owner_client


def _seed_cash_venta_expense_and_qr(shop, client) -> None:
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    venta = client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": "100",
            "reason": "venta mostrador",
            "category": "venta",
            "method": "cash",
        },
    )
    assert venta.status_code == 200

    expense = client.post(
        "/api/cash",
        json={
            "direction": "out",
            "amount": "30",
            "reason": "insumos",
            "category": "gasto",
            "method": "cash",
        },
    )
    assert expense.status_code == 200

    payment = Payment(
        id=uuid4(),
        tenant_id=shop.store.tenant_id,
        order_id=None,
        provider="fake",
        provider_ref=f"pay-{uuid4().hex[:8]}",
        amount=Decimal("80.00"),
        currency="BOB",
        status=PaymentStatus.PENDING,
        qr_payload="QR:test",
    )
    shop.store.payments[payment.id] = payment
    shop.store.payments_by_ref[payment.provider_ref] = payment
    shop.store.confirm_from_adapter(payment.provider_ref)


def test_trial_balance_balanced_after_cash_expense_and_qr() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_venta_expense_and_qr(shop, client)

    tenant = shop.store.tenant_id
    ensure_chart_seed(shop.store, tenant)
    accounts = shop.store.list_chart_accounts(tenant)
    entries = shop.store.list_journal_entries(tenant)

    result = trial_balance(entries, accounts)
    assert result["balanced"] is True
    assert result["total_debit"] == result["total_credit"]
    assert result["total_debit"] == Decimal("210")

    by_code = {row["code"]: row for row in result["rows"]}
    assert by_code["4100"]["credit"] == Decimal("180")  # Ventas: 100 cash + 80 QR
    assert by_code["4100"]["debit"] == Decimal("0")
    assert by_code["1100"]["debit"] == Decimal("100")  # Caja in
    assert by_code["1100"]["credit"] == Decimal("30")  # Caja out expense
    assert by_code["1200"]["debit"] == Decimal("80")  # Banco QR
    assert by_code["5100"]["debit"] == Decimal("30")  # Gastos


def test_void_cash_venta_nets_trial_and_mayor() -> None:
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    posted = client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": "50",
            "reason": "venta",
            "category": "venta",
            "method": "cash",
        },
    )
    assert posted.status_code == 200
    mid = posted.json()["id"]
    voided = client.post(f"/api/cash/{mid}/void", json={"reason": "duplicado"})
    assert voided.status_code == 200

    tenant = shop.store.tenant_id
    ensure_chart_seed(shop.store, tenant)
    accounts = shop.store.list_chart_accounts(tenant)
    entries = shop.store.list_journal_entries(tenant)

    tb = trial_balance(entries, accounts)
    assert tb["balanced"] is True
    by_code = {row["code"]: row for row in tb["rows"]}
    assert by_code["1100"]["debit"] == by_code["1100"]["credit"] == Decimal("50")
    assert by_code["4100"]["debit"] == by_code["4100"]["credit"] == Decimal("50")

    ledger = general_ledger(entries, accounts, account_code="1100")
    assert len(ledger["accounts"]) == 1
    caja = ledger["accounts"][0]
    assert caja["code"] == "1100"
    assert caja["closing_balance"] == Decimal("0")
    assert len(caja["lines"]) == 2
    assert caja["lines"][-1]["balance"] == Decimal("0")


def test_income_statement_managerial_with_cogs_field() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_venta_expense_and_qr(shop, client)

    tenant = shop.store.tenant_id
    ensure_chart_seed(shop.store, tenant)
    accounts = shop.store.list_chart_accounts(tenant)
    entries = shop.store.list_journal_entries(tenant)

    stmt = income_statement(entries, accounts)
    assert stmt["revenue"] == Decimal("180")
    assert stmt["cogs"] == Decimal("0")
    assert stmt["expenses"] == Decimal("30")
    assert stmt["draws"] == Decimal("0")
    assert stmt["result"] == Decimal("150")
    assert stmt["currency"] == "BOB"
    assert "COGS" in stmt["note"] or "cogs" in stmt["note"].lower()


def test_journal_report_apis_smoke() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_venta_expense_and_qr(shop, client)

    tb = client.get("/api/journal/trial-balance", params={"period": "month"})
    assert tb.status_code == 200
    body = tb.json()
    assert body["balanced"] is True
    assert "rows" in body
    assert Decimal(body["total_debit"]) == Decimal(body["total_credit"])

    ledger = client.get("/api/journal/ledger", params={"period": "month", "account": "4100"})
    assert ledger.status_code == 200
    ledger_body = ledger.json()
    assert len(ledger_body["accounts"]) == 1
    assert ledger_body["accounts"][0]["code"] == "4100"

    income = client.get("/api/journal/income", params={"period": "month"})
    assert income.status_code == 200
    income_body = income.json()
    assert Decimal(income_body["revenue"]) == Decimal("180")
    assert Decimal(income_body["result"]) == Decimal("150")
    assert income_body["note"]
