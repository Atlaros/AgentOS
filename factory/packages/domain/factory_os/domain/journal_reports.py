"""Managerial general ledger, trial balance, and income statement (ADR-011 Fase 2)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Sequence

from factory_os.domain.journal import line_amount, line_direction
from factory_os.domain.models import ChartAccount, JournalEntry

# Debit-normal accounts: debit increases running balance.
_DEBIT_NORMAL = frozenset({"asset", "expense", "equity_draw"})
# Credit-normal accounts: credit increases running balance.
_CREDIT_NORMAL = frozenset({"income", "liability", "equity"})

_COGS_CODE = "5110"
_MANAGERIAL_NOTE = "Incluye COGS cuando el costo de compra es conocido; utilidad gerencial"


def _account_code(line: Any, accounts_by_id: Mapping[Any, ChartAccount]) -> str:
    code = getattr(line, "account_code", None)
    if isinstance(line, Mapping):
        code = line.get("account_code") or code
    if code:
        return str(code).strip()
    account_id = getattr(line, "account_id", None)
    if isinstance(line, Mapping):
        account_id = line.get("account_id", account_id)
    if account_id is not None and account_id in accounts_by_id:
        return accounts_by_id[account_id].code
    return ""


def _signed_delta(account_type: str, direction: str, amount: Decimal) -> Decimal:
    """Return signed change for running balance (positive = natural increase)."""
    kind = (account_type or "").strip()
    if kind in _DEBIT_NORMAL:
        return amount if direction == "debit" else -amount
    if kind in _CREDIT_NORMAL:
        return amount if direction == "credit" else -amount
    # Unknown type: treat as debit-normal.
    return amount if direction == "debit" else -amount


def trial_balance(
    entries: Sequence[JournalEntry],
    accounts: Sequence[ChartAccount],
) -> dict[str, Any]:
    """Sum debit and credit lines per account for the given entries (period already filtered)."""
    accounts_by_id = {account.id: account for account in accounts}
    accounts_by_code = {account.code: account for account in accounts}
    totals: dict[str, dict[str, Decimal]] = {
        account.code: {"debit": Decimal("0"), "credit": Decimal("0")} for account in accounts
    }

    for entry in entries:
        for line in entry.lines or []:
            code = _account_code(line, accounts_by_id)
            if not code:
                continue
            if code not in totals:
                totals[code] = {"debit": Decimal("0"), "credit": Decimal("0")}
            direction = line_direction(line)
            amount = line_amount(line)
            if direction == "debit":
                totals[code]["debit"] += amount
            elif direction == "credit":
                totals[code]["credit"] += amount

    rows: list[dict[str, Any]] = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for code in sorted(totals.keys()):
        debit = totals[code]["debit"]
        credit = totals[code]["credit"]
        if debit == 0 and credit == 0:
            continue
        account = accounts_by_code.get(code)
        name = account.name if account is not None else code
        rows.append({"code": code, "name": name, "debit": debit, "credit": credit})
        total_debit += debit
        total_credit += credit

    return {
        "rows": rows,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "balanced": total_debit == total_credit,
    }


def general_ledger(
    entries: Sequence[JournalEntry],
    accounts: Sequence[ChartAccount],
    account_code: str | None = None,
) -> dict[str, Any]:
    """Build mayor with running balance; optional single-account filter."""
    accounts_by_id = {account.id: account for account in accounts}
    accounts_by_code = {account.code: account for account in accounts}
    wanted = (account_code or "").strip() or None

    # Collect chronological lines per account.
    buckets: dict[str, list[dict[str, Any]]] = {}
    for entry in sorted(entries, key=lambda item: (item.entry_at, str(item.id))):
        for line in entry.lines or []:
            code = _account_code(line, accounts_by_id)
            if not code:
                continue
            if wanted is not None and code != wanted:
                continue
            buckets.setdefault(code, []).append(
                {
                    "entry_at": entry.entry_at,
                    "entry_id": entry.id,
                    "kind": entry.kind,
                    "memo": entry.memo or "",
                    "direction": line_direction(line),
                    "amount": line_amount(line),
                }
            )

    account_rows: list[dict[str, Any]] = []
    for code in sorted(buckets.keys()):
        account = accounts_by_code.get(code)
        account_type = account.account_type if account is not None else "asset"
        name = account.name if account is not None else code
        running = Decimal("0")
        lines_out: list[dict[str, Any]] = []
        for raw in buckets[code]:
            direction = raw["direction"]
            amount = raw["amount"]
            running += _signed_delta(account_type, direction, amount)
            lines_out.append(
                {
                    "entry_at": raw["entry_at"],
                    "entry_id": raw["entry_id"],
                    "kind": raw["kind"],
                    "memo": raw["memo"],
                    "debit": amount if direction == "debit" else Decimal("0"),
                    "credit": amount if direction == "credit" else Decimal("0"),
                    "balance": running,
                }
            )
        account_rows.append(
            {
                "code": code,
                "name": name,
                "opening": Decimal("0"),
                "lines": lines_out,
                "closing_balance": running,
            }
        )

    return {"accounts": account_rows}


def income_statement(
    entries: Sequence[JournalEntry],
    accounts: Sequence[ChartAccount],
) -> dict[str, Any]:
    """Managerial P&L: revenue − cogs − expenses − draws."""
    accounts_by_id = {account.id: account for account in accounts}
    type_by_code = {account.code: account.account_type for account in accounts}

    revenue = Decimal("0")
    cogs = Decimal("0")
    expenses = Decimal("0")
    draws = Decimal("0")
    currency = "BOB"

    for entry in entries:
        for line in entry.lines or []:
            code = _account_code(line, accounts_by_id)
            if not code:
                continue
            account_type = type_by_code.get(code, "")
            amount = line_amount(line)
            direction = line_direction(line)
            if getattr(line, "currency", None):
                currency = str(line.currency) or currency
            elif isinstance(line, Mapping) and line.get("currency"):
                currency = str(line["currency"]) or currency

            if account_type == "income":
                # Net credit on income accounts.
                revenue += amount if direction == "credit" else -amount
            elif code == _COGS_CODE:
                cogs += amount if direction == "debit" else -amount
            elif account_type == "expense":
                expenses += amount if direction == "debit" else -amount
            elif account_type == "equity_draw":
                draws += amount if direction == "debit" else -amount

    return {
        "revenue": revenue,
        "cogs": cogs,
        "expenses": expenses,
        "draws": draws,
        "result": revenue - cogs - expenses - draws,
        "currency": currency,
        "note": _MANAGERIAL_NOTE,
    }


def balance_sheet(
    entries: Sequence[JournalEntry],
    accounts: Sequence[ChartAccount],
) -> dict[str, Any]:
    """Managerial balance sheet from closing balances (same rules as mayor)."""
    ledger = general_ledger(entries, accounts)
    accounts_by_code = {account.code: account for account in accounts}
    type_totals = {
        "asset": Decimal("0"),
        "liability": Decimal("0"),
        "equity": Decimal("0"),
        "equity_draw": Decimal("0"),
        "income": Decimal("0"),
        "expense": Decimal("0"),
    }
    rows: list[dict[str, Any]] = []
    for account_row in ledger["accounts"]:
        code = account_row["code"]
        account = accounts_by_code.get(code)
        account_type = account.account_type if account is not None else "asset"
        closing = Decimal(str(account_row["closing_balance"]))
        if closing == 0:
            continue
        type_totals[account_type] = type_totals.get(account_type, Decimal("0")) + closing
        rows.append(
            {
                "code": code,
                "name": account_row["name"],
                "account_type": account_type,
                "balance": closing,
            }
        )

    assets = type_totals.get("asset", Decimal("0"))
    liabilities = type_totals.get("liability", Decimal("0"))
    equity = type_totals.get("equity", Decimal("0"))
    equity_draws = type_totals.get("equity_draw", Decimal("0"))
    # Net income (income − expense − draws already in P&L sense) closes into equity check.
    net_income = type_totals.get("income", Decimal("0")) - type_totals.get("expense", Decimal("0"))
    equity_side = liabilities + equity + net_income - equity_draws
    balanced_check = assets == equity_side

    return {
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "equity_draws": equity_draws,
        "net_income": net_income,
        "balanced_check": balanced_check,
        "rows": rows,
        "by_type": {
            "asset": [row for row in rows if row["account_type"] == "asset"],
            "liability": [row for row in rows if row["account_type"] == "liability"],
            "equity": [row for row in rows if row["account_type"] == "equity"],
            "equity_draw": [row for row in rows if row["account_type"] == "equity_draw"],
            "income": [row for row in rows if row["account_type"] == "income"],
            "expense": [row for row in rows if row["account_type"] == "expense"],
        },
    }


def trial_balance_to_csv(payload: Mapping[str, Any]) -> str:
    """Flatten trial balance rows to CSV (amounts as strings)."""
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=("code", "name", "debit", "credit"),
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in payload.get("rows") or []:
        writer.writerow(
            {
                "code": row.get("code") or "",
                "name": row.get("name") or "",
                "debit": str(row.get("debit", "")),
                "credit": str(row.get("credit", "")),
            }
        )
    writer.writerow(
        {
            "code": "",
            "name": "TOTAL",
            "debit": str(payload.get("total_debit", "")),
            "credit": str(payload.get("total_credit", "")),
        }
    )
    return buffer.getvalue()
