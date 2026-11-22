"""Light bank reconciliation suggestions (ADR-011 Fase 3)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from factory_os.domain.chart_accounts import ensure_chart_seed
from factory_os.domain.journal import line_amount, line_direction
from factory_os.domain.models import PaymentStatus
from factory_os.domain.store import CommerceStore

_BANCO = "1200"
_MATCH_TOLERANCE = Decimal("0.01")


def _as_utc_day(stamp: datetime | date | None) -> date | None:
    if stamp is None:
        return None
    if isinstance(stamp, date) and not isinstance(stamp, datetime):
        return stamp
    if isinstance(stamp, datetime):
        when = stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=UTC)
        return when.astimezone(UTC).date()
    return None


def _in_range(day: date | None, date_from: date | None, date_to: date | None) -> bool:
    if day is None:
        return False
    if date_from is not None and day < date_from:
        return False
    if date_to is not None and day > date_to:
        return False
    return True


def bank_recon_suggest(
    store: CommerceStore,
    tenant_id: UUID,
    date_from: date | None,
    date_to: date | None,
) -> dict[str, Any]:
    """Match Banco journal lines to confirmed non-cash payments by amount+UTC day."""
    store.require_tenant(tenant_id)
    ensure_chart_seed(store, tenant_id)
    accounts = {account.code: account for account in store.list_chart_accounts(tenant_id)}
    banco = accounts.get(_BANCO)

    bank_lines: list[dict[str, Any]] = []
    for entry in store.list_journal_entries(tenant_id):
        day = _as_utc_day(entry.entry_at)
        if not _in_range(day, date_from, date_to):
            continue
        for line in entry.lines or []:
            code = getattr(line, "account_code", None)
            if not code and banco is not None and line.account_id == banco.id:
                code = _BANCO
            if str(code or "") != _BANCO:
                continue
            bank_lines.append(
                {
                    "entry_id": entry.id,
                    "entry_at": entry.entry_at,
                    "direction": line_direction(line),
                    "amount": line_amount(line),
                    "currency": getattr(line, "currency", None) or "BOB",
                    "memo": entry.memo or "",
                    "origin_source": entry.origin_source,
                    "origin_id": entry.origin_id,
                    "matched": False,
                }
            )

    payments: list[dict[str, Any]] = []
    for payment in store.list_payments(tenant_id):
        if payment.status is not PaymentStatus.CONFIRMED:
            continue
        if str(payment.provider or "").strip().lower() == "cash":
            continue
        day = _as_utc_day(payment.created_at)
        if not _in_range(day, date_from, date_to):
            continue
        payments.append(
            {
                "payment_id": payment.id,
                "created_at": payment.created_at,
                "amount": Decimal(str(payment.amount)),
                "currency": payment.currency or "BOB",
                "provider": payment.provider,
                "matched": False,
            }
        )

    matches: list[dict[str, Any]] = []
    used_payments: set[UUID] = set()
    for bank in bank_lines:
        bank_day = _as_utc_day(bank["entry_at"])
        bank_amount = Decimal(str(bank["amount"]))
        for pay in payments:
            pay_id = pay["payment_id"]
            if pay_id in used_payments:
                continue
            if _as_utc_day(pay["created_at"]) != bank_day:
                continue
            delta = abs(Decimal(str(pay["amount"])) - bank_amount)
            if delta > _MATCH_TOLERANCE:
                continue
            used_payments.add(pay_id)
            bank["matched"] = True
            pay["matched"] = True
            matches.append(
                {
                    "entry_id": bank["entry_id"],
                    "payment_id": pay_id,
                    "amount": bank_amount,
                    "day": bank_day.isoformat() if bank_day else None,
                }
            )
            break

    return {
        "bank_lines": bank_lines,
        "payments": payments,
        "matches": matches,
    }
