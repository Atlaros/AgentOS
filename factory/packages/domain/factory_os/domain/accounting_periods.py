"""Accounting period close lock for journal posting (ADR-011 Fase 2)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID


def entry_utc_date(entry_at: Any) -> date:
    """Normalize entry_at to a UTC calendar date."""
    if isinstance(entry_at, date) and not isinstance(entry_at, datetime):
        return entry_at
    if isinstance(entry_at, datetime):
        stamp = entry_at
    elif entry_at is None:
        stamp = datetime.now(UTC)
    else:
        stamp = datetime.fromisoformat(str(entry_at).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC).date()


def assert_period_open_for_entry(store: Any, tenant_id: UUID, entry_at: Any) -> None:
    """Raise ValueError('period_closed') when a closed period covers entry_at's UTC date."""
    store.require_tenant(tenant_id)
    day = entry_utc_date(entry_at)
    for period in store.list_accounting_periods(tenant_id):
        if period.status != "closed":
            continue
        if period.date_from <= day <= period.date_to:
            raise ValueError("period_closed")
