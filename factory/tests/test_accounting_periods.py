"""T7 Contabilidad: period close blocks journal posts (ADR-011 Fase 2)."""

from __future__ import annotations

from calendar import monthrange
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from factory_os.domain.chart_accounts import ensure_chart_seed
from factory_os.domain.journal_posting import post_cash_movement
from factory_os.domain.models import CashMovement, PILOT_TENANT_ID
from tests.conftest import make_shop, owner_client


def _month_bounds(today: date | None = None) -> tuple[date, date]:
    day = today or datetime.now(UTC).date()
    last = monthrange(day.year, day.month)[1]
    return date(day.year, day.month, 1), date(day.year, day.month, last)


def _cash_lines(amount: str = "25") -> list[dict]:
    money = Decimal(amount)
    return [
        {"account_code": "1100", "direction": "debit", "amount": money, "currency": "BOB"},
        {"account_code": "4100", "direction": "credit", "amount": money, "currency": "BOB"},
    ]


def test_close_period_blocks_new_journal_entry() -> None:
    shop = make_shop()
    tenant = PILOT_TENANT_ID
    ensure_chart_seed(shop.store, tenant)
    date_from, date_to = _month_bounds()
    closed = shop.store.close_accounting_period(
        tenant, date_from=date_from, date_to=date_to, closed_by_name="Dueño"
    )
    assert closed.status == "closed"

    with pytest.raises(ValueError, match="period_closed"):
        shop.store.add_journal_entry(
            tenant,
            entry_at=datetime.now(UTC),
            origin_source="cash",
            origin_id=uuid4(),
            kind="post",
            memo="blocked",
            lines=_cash_lines(),
        )


def test_close_period_blocks_post_cash_movement() -> None:
    shop = make_shop()
    tenant = PILOT_TENANT_ID
    ensure_chart_seed(shop.store, tenant)
    date_from, date_to = _month_bounds()
    shop.store.close_accounting_period(
        tenant, date_from=date_from, date_to=date_to, closed_by_name="Dueño"
    )
    movement = CashMovement(
        id=uuid4(),
        tenant_id=tenant,
        direction="in",
        amount=Decimal("40"),
        currency="BOB",
        reason="venta",
        category="venta",
        method="cash",
        created_at=datetime.now(UTC),
    )
    with pytest.raises(ValueError, match="period_closed"):
        post_cash_movement(shop.store, movement)


def test_reopen_period_allows_posting_again() -> None:
    shop = make_shop()
    tenant = PILOT_TENANT_ID
    ensure_chart_seed(shop.store, tenant)
    date_from, date_to = _month_bounds()
    shop.store.close_accounting_period(
        tenant, date_from=date_from, date_to=date_to, closed_by_name="Dueño"
    )
    shop.store.reopen_accounting_period(tenant, date_from=date_from, date_to=date_to)

    entry = shop.store.add_journal_entry(
        tenant,
        entry_at=datetime.now(UTC),
        origin_source="cash",
        origin_id=uuid4(),
        kind="post",
        memo="after reopen",
        lines=_cash_lines("15"),
    )
    assert entry.id is not None
    assert len(entry.lines) == 2


def test_get_periods_lists_closed() -> None:
    shop = make_shop()
    client = owner_client(shop)
    date_from, date_to = _month_bounds()
    closed = client.post(
        "/api/journal/periods/close",
        json={"from": date_from.isoformat(), "to": date_to.isoformat()},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    listed = client.get("/api/journal/periods")
    assert listed.status_code == 200
    periods = listed.json()["periods"]
    assert any(
        item["status"] == "closed"
        and item["from"] == date_from.isoformat()
        and item["to"] == date_to.isoformat()
        for item in periods
    )

    reopened = client.post(
        "/api/journal/periods/reopen",
        json={"from": date_from.isoformat(), "to": date_to.isoformat()},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"
