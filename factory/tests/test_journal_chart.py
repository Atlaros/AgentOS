"""T1 Contabilidad: chart seed + balanced journal store APIs (ADR-011)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from factory_os.domain.chart_accounts import SEED_ACCOUNTS, ensure_chart_seed
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.store import MemoryCommerceStore


def _shop() -> MemoryCommerceStore:
    return MemoryCommerceStore(PILOT_TENANT_ID)


def test_ensure_chart_seed_creates_seed_accounts() -> None:
    store = _shop()
    ensure_chart_seed(store, PILOT_TENANT_ID)
    accounts = store.list_chart_accounts(PILOT_TENANT_ID)
    codes = sorted(account.code for account in accounts)
    expected = sorted(item["code"] for item in SEED_ACCOUNTS)
    assert len(accounts) == len(SEED_ACCOUNTS)
    assert codes == expected
    assert "5110" in codes
    assert "1400" in codes


def test_ensure_chart_seed_is_idempotent() -> None:
    store = _shop()
    ensure_chart_seed(store, PILOT_TENANT_ID)
    ensure_chart_seed(store, PILOT_TENANT_ID)
    assert len(store.list_chart_accounts(PILOT_TENANT_ID)) == len(SEED_ACCOUNTS)


def test_add_balanced_journal_entry_succeeds() -> None:
    store = _shop()
    ensure_chart_seed(store, PILOT_TENANT_ID)
    origin_id = uuid4()
    entry = store.add_journal_entry(
        PILOT_TENANT_ID,
        entry_at=datetime.now(UTC),
        origin_source="cash",
        origin_id=origin_id,
        kind="post",
        memo="venta efectivo",
        lines=[
            {"account_code": "1100", "direction": "debit", "amount": Decimal("100"), "currency": "BOB"},
            {"account_code": "4100", "direction": "credit", "amount": Decimal("100"), "currency": "BOB"},
        ],
    )
    assert len(entry.lines) == 2
    loaded = store.get_journal_by_origin(PILOT_TENANT_ID, "cash", origin_id, "post")
    assert loaded is not None
    assert loaded.id == entry.id
    listed = store.list_journal_entries(PILOT_TENANT_ID)
    assert len(listed) == 1
    assert len(listed[0].lines) == 2


def test_unbalanced_journal_entry_raises() -> None:
    store = _shop()
    ensure_chart_seed(store, PILOT_TENANT_ID)
    with pytest.raises(ValueError):
        store.add_journal_entry(
            PILOT_TENANT_ID,
            entry_at=datetime.now(UTC),
            origin_source="cash",
            origin_id=uuid4(),
            kind="post",
            memo="bad",
            lines=[
                {"account_code": "1100", "direction": "debit", "amount": Decimal("100"), "currency": "BOB"},
                {"account_code": "4100", "direction": "credit", "amount": Decimal("50"), "currency": "BOB"},
            ],
        )


def test_duplicate_origin_kind_returns_same_entry_id() -> None:
    store = _shop()
    ensure_chart_seed(store, PILOT_TENANT_ID)
    origin_id = uuid4()
    kwargs = dict(
        entry_at=datetime.now(UTC),
        origin_source="payment",
        origin_id=origin_id,
        kind="post",
        memo="qr",
        lines=[
            {"account_code": "1200", "direction": "debit", "amount": Decimal("80"), "currency": "BOB"},
            {"account_code": "4100", "direction": "credit", "amount": Decimal("80"), "currency": "BOB"},
        ],
    )
    first = store.add_journal_entry(PILOT_TENANT_ID, **kwargs)
    second = store.add_journal_entry(PILOT_TENANT_ID, **kwargs)
    assert first.id == second.id
    assert len(store.list_journal_entries(PILOT_TENANT_ID)) == 1
