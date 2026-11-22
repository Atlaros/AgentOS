"""Multi-sheet Contabilidad monthly package (ADR-011 Export Fase C)."""

from __future__ import annotations

import io
from dataclasses import replace
from typing import Any

from factory_os.domain.journal_export import (
    JournalExportHeader,
    REPORT_TYPE_BALANCE,
    REPORT_TYPE_COMPROBACION,
    REPORT_TYPE_DIARIO,
    REPORT_TYPE_HECHOS,
    REPORT_TYPE_MAYOR,
    REPORT_TYPE_RESULTADO,
    balance_to_xlsx,
    entries_to_xlsx,
    income_to_xlsx,
    ledger_to_xlsx,
    trial_balance_to_xlsx,
)
from factory_os.domain.ledger_export import hechos_to_xlsx

PACKAGE_SHEET_ORDER = (
    "Diario",
    "Mayor",
    "Comprobación",
    "Resultado",
    "Balance",
    "Hechos",
)


def _header_for(base: JournalExportHeader, report_type: str) -> JournalExportHeader:
    return replace(base, report_type=report_type)


def _copy_sheet_values(source: Any, target: Any) -> None:
    for row in source.iter_rows():
        for cell in row:
            target.cell(row=cell.row, column=cell.column, value=cell.value)
    if source.freeze_panes:
        target.freeze_panes = source.freeze_panes


def merge_xlsx_sheets(parts: list[tuple[str, bytes]]) -> bytes:
    """Merge single-sheet workbooks into one multi-sheet workbook (Spanish titles)."""
    from openpyxl import Workbook, load_workbook

    book = Workbook()
    book.remove(book.active)
    for title, payload in parts:
        src = load_workbook(io.BytesIO(payload))
        dest = book.create_sheet(title[:31])
        _copy_sheet_values(src.active, dest)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def build_accounting_package_xlsx(
    *,
    journal_entries: list[dict[str, Any]],
    mayor: dict[str, Any],
    trial: dict[str, Any],
    income: dict[str, Any],
    balance: dict[str, Any],
    hechos_entries: list[dict[str, Any]],
    header: JournalExportHeader,
) -> bytes:
    """One workbook: Diario, Mayor, Comprobación, Resultado, Balance, Hechos.

    Reuses the same per-view xlsx builders (no second accounting logic).
    """
    parts = [
        (
            "Diario",
            entries_to_xlsx(
                journal_entries,
                header=_header_for(header, REPORT_TYPE_DIARIO),
            ),
        ),
        (
            "Mayor",
            ledger_to_xlsx(mayor, header=_header_for(header, REPORT_TYPE_MAYOR)),
        ),
        (
            "Comprobación",
            trial_balance_to_xlsx(
                trial,
                header=_header_for(header, REPORT_TYPE_COMPROBACION),
            ),
        ),
        (
            "Resultado",
            income_to_xlsx(income, header=_header_for(header, REPORT_TYPE_RESULTADO)),
        ),
        (
            "Balance",
            balance_to_xlsx(balance, header=_header_for(header, REPORT_TYPE_BALANCE)),
        ),
        (
            "Hechos",
            hechos_to_xlsx(
                hechos_entries,
                header=_header_for(header, REPORT_TYPE_HECHOS),
            ),
        ),
    ]
    # Keep declared order even if a future caller reorders the list.
    by_title = {title: payload for title, payload in parts}
    ordered = [(title, by_title[title]) for title in PACKAGE_SHEET_ORDER]
    return merge_xlsx_sheets(ordered)
