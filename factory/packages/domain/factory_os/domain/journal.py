"""Journal helpers for double-entry balance checks and read models (ADR-011)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence
from uuid import UUID

from factory_os.domain.models import JournalEntry
from factory_os.domain.store import CommerceStore

ORIGIN_SOURCES = frozenset(
    {"cash", "payment", "purchase", "cogs", "adjustment", "supplier_payment"}
)
JOURNAL_KINDS = frozenset({"post", "reverse"})
LINE_DIRECTIONS = frozenset({"debit", "credit"})

_ORIGIN_HREF = {
    "cash": "/cash?tab=movements",
    "payment": "/orders",
    "purchase": "/suppliers",
    "supplier_payment": "/suppliers",
}


def line_amount(line: Mapping[str, Any] | Any) -> Decimal:
    if isinstance(line, Mapping):
        return Decimal(str(line["amount"]))
    return Decimal(str(line.amount))


def line_direction(line: Mapping[str, Any] | Any) -> str:
    if isinstance(line, Mapping):
        return str(line["direction"])
    return str(line.direction)


def sum_by_direction(lines: Sequence[Mapping[str, Any] | Any], direction: str) -> Decimal:
    total = Decimal("0")
    for line in lines:
        if line_direction(line) == direction:
            total += line_amount(line)
    return total


def assert_journal_balanced(lines: Sequence[Mapping[str, Any] | Any]) -> None:
    if len(lines) < 2:
        raise ValueError("journal_needs_two_lines")
    debits = sum_by_direction(lines, "debit")
    credits = sum_by_direction(lines, "credit")
    if debits != credits or debits <= 0:
        raise ValueError("unbalanced_journal")


def origin_href(origin_source: str) -> str | None:
    """Best-effort panel link for the operational origin of a journal entry."""
    return _ORIGIN_HREF.get((origin_source or "").strip().lower())


def filter_journal_entries(
    entries: Sequence[JournalEntry],
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[JournalEntry]:
    """Filter journal entries by inclusive UTC calendar day of ``entry_at``."""
    filtered: list[JournalEntry] = []
    for entry in entries:
        day = _entry_day_utc(entry.entry_at)
        if date_from is not None or date_to is not None:
            if day is None:
                continue
            if date_from is not None and day < date_from:
                continue
            if date_to is not None and day > date_to:
                continue
        filtered.append(entry)
    return filtered


def hydrate_journal_entry(store: CommerceStore, tenant_id: UUID, entry: JournalEntry) -> dict[str, Any]:
    """Serialize a journal entry with account names and origin href for the panel."""
    store.require_tenant(tenant_id)
    accounts = {account.code: account for account in store.list_chart_accounts(tenant_id)}
    lines_payload: list[dict[str, Any]] = []
    for line in entry.lines or []:
        code = (line.account_code or "").strip()
        if not code:
            for account in accounts.values():
                if account.id == line.account_id:
                    code = account.code
                    break
        name = accounts[code].name if code in accounts else code
        lines_payload.append(
            {
                "account_code": code,
                "account_name": name,
                "direction": line.direction,
                "amount": str(line.amount),
                "currency": line.currency or "BOB",
            }
        )
    return {
        "id": str(entry.id),
        "entry_at": entry.entry_at.isoformat() if entry.entry_at else None,
        "origin_source": entry.origin_source,
        "origin_id": str(entry.origin_id),
        "kind": entry.kind,
        "memo": entry.memo or "",
        "origin_href": origin_href(entry.origin_source),
        "lines": lines_payload,
    }


def _entry_day_utc(raw: datetime | None) -> date | None:
    if raw is None:
        return None
    created = raw
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return created.astimezone(UTC).date()
