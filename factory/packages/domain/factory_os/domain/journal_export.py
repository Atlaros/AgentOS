"""CSV/PDF/XLSX export for the managerial journal (ADR-011 Export Fase A)."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

BUSINESS_TZ = ZoneInfo("America/La_Paz")
EMPTY_PERIOD_NOTICE = "Sin movimientos en el período"
FINANCIAL_PDF_FOOTER = "Contabilidad gerencial. No sustituye estados financieros oficiales."
REPORT_TYPE_DIARIO = "Diario"
REPORT_TYPE_MAYOR = "Mayor"
REPORT_TYPE_RESULTADO = "Resultado"
REPORT_TYPE_BALANCE = "Balance"
REPORT_TYPE_COMPROBACION = "Comprobación"
REPORT_TYPE_CONCILIACION = "Conciliación"
REPORT_TYPE_HECHOS = "Hechos"
REPORT_TYPE_PAQUETE = "Paquete contable"

# report_download_log.report_id values for Contabilidad exports (ADR-011 Fase B/C).
DOWNLOAD_REPORT_JOURNAL = "journal"
DOWNLOAD_REPORT_LEDGER_HECHOS = "ledger_hechos"
DOWNLOAD_REPORT_MAYOR = "mayor"
DOWNLOAD_REPORT_RESULTADO = "resultado"
DOWNLOAD_REPORT_BALANCE = "balance"
DOWNLOAD_REPORT_COMPROBACION = "comprobacion"
DOWNLOAD_REPORT_CONCILIACION = "conciliacion"
DOWNLOAD_REPORT_ACCOUNTING_PACKAGE = "accounting_package"

LEDGER_DOWNLOAD_REPORT_IDS = frozenset(
    {
        DOWNLOAD_REPORT_JOURNAL,
        DOWNLOAD_REPORT_LEDGER_HECHOS,
        DOWNLOAD_REPORT_MAYOR,
        DOWNLOAD_REPORT_RESULTADO,
        DOWNLOAD_REPORT_BALANCE,
        DOWNLOAD_REPORT_COMPROBACION,
        DOWNLOAD_REPORT_CONCILIACION,
        DOWNLOAD_REPORT_ACCOUNTING_PACKAGE,
    }
)

_INCOME_ROWS = (
    ("revenue", "Ingresos (Ventas)"),
    ("cogs", "Costo de ventas"),
    ("expenses", "Gastos"),
    ("draws", "Retiros"),
    ("result", "Resultado gerencial"),
)

_BALANCE_SUMMARY_ROWS = (
    ("assets", "Activos"),
    ("liabilities", "Pasivos"),
    ("equity", "Patrimonio"),
    ("equity_draws", "Retiros"),
)

_BALANCE_TYPE_LABEL = {
    "asset": "Activo",
    "liability": "Pasivo",
    "equity": "Patrimonio",
    "equity_draw": "Retiros",
    "income": "Ingresos",
    "expense": "Gastos",
}

_BALANCE_FIELDS = (
    "código",
    "cuenta",
    "tipo",
    "saldo",
)

_CSV_FIELDS = (
    "fecha",
    "asiento",
    "cuenta",
    "descripción",
    "debe",
    "haber",
    "origen",
)

_MAYOR_FIELDS = (
    "fecha",
    "tipo",
    "memo",
    "debe",
    "haber",
    "saldo",
)

_TRIAL_FIELDS = (
    "código",
    "cuenta",
    "debe",
    "haber",
)

_RECON_BANCO_FIELDS = (
    "fecha",
    "sentido",
    "monto",
    "memo",
    "match",
)

_RECON_PAGO_FIELDS = (
    "fecha",
    "proveedor",
    "monto",
    "match",
)

_RECON_MATCH_FIELDS = (
    "asiento",
    "pago",
    "monto",
    "día",
)


@dataclass(frozen=True)
class JournalExportHeader:
    """File header block for Contabilidad exports (Spanish labels in the file)."""

    business_name: str
    report_type: str
    period_label: str
    generated_at: str
    actor_name: str
    period_closed: bool = False


def export_filename_slug(business_name: str, report_key: str, ext: str) -> str:
    """Build a Content-Disposition filename from shop name (never 'agentia')."""
    base = re.sub(r"[^a-z0-9]+", "-", (business_name or "").casefold()).strip("-")
    if not base or base == "agentia":
        base = "tienda"
    report = re.sub(r"[^a-z0-9]+", "-", (report_key or "diario").casefold()).strip("-") or "diario"
    suffix = (ext or "xlsx").lstrip(".").lower()
    return f"{base}-{report}.{suffix}"


def format_generated_at(moment: datetime | None = None) -> str:
    """Timestamp label in America/La_Paz for export headers."""
    now = moment if moment is not None else datetime.now(BUSINESS_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=BUSINESS_TZ)
    else:
        now = now.astimezone(BUSINESS_TZ)
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")


def flatten_journal_lines(hydrated_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One export row per journal line with Spanish column keys and Debe/Haber split."""
    rows: list[dict[str, Any]] = []
    for entry in hydrated_rows:
        fecha = entry.get("entry_at") or ""
        asiento = entry.get("id") or ""
        kind = entry.get("kind") or ""
        memo = entry.get("memo") or ""
        origen_source = entry.get("origin_source") or ""
        origen_id = entry.get("origin_id") or ""
        origen = f"{origen_source}:{origen_id}".strip(":")
        if kind:
            origen = f"{origen} ({kind})" if origen else kind
        lines = entry.get("lines") or []
        if not lines:
            rows.append(
                {
                    "fecha": fecha,
                    "asiento": asiento,
                    "cuenta": "",
                    "descripción": memo,
                    "debe": "",
                    "haber": "",
                    "origen": origen,
                }
            )
            continue
        for line in lines:
            code = line.get("account_code") or ""
            name = line.get("account_name") or ""
            cuenta = f"{code} {name}".strip()
            direction = (line.get("direction") or "").strip().lower()
            amount = line.get("amount")
            debe = ""
            haber = ""
            if direction == "debit":
                debe = amount if amount is not None else ""
            elif direction == "credit":
                haber = amount if amount is not None else ""
            rows.append(
                {
                    "fecha": fecha,
                    "asiento": asiento,
                    "cuenta": cuenta,
                    "descripción": memo,
                    "debe": debe,
                    "haber": haber,
                    "origen": origen,
                }
            )
    return rows


def _as_decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def journal_totals(flat_rows: list[dict[str, Any]]) -> tuple[Decimal, Decimal]:
    total_debe = sum((_as_decimal(row.get("debe")) for row in flat_rows), Decimal("0"))
    total_haber = sum((_as_decimal(row.get("haber")) for row in flat_rows), Decimal("0"))
    return total_debe, total_haber


def _header_pairs(header: JournalExportHeader) -> list[tuple[str, str]]:
    closed = "Sí" if header.period_closed else "No"
    return [
        ("Negocio", header.business_name),
        ("Tipo de reporte", header.report_type),
        ("Período", header.period_label),
        ("Generado", header.generated_at),
        ("Actor", header.actor_name),
        ("Período cerrado", closed),
    ]


def entries_to_csv(
    hydrated_rows: list[dict[str, Any]],
    *,
    header: JournalExportHeader | None = None,
) -> str:
    """Flatten journal entries to CSV with Spanish columns (and optional header block)."""
    buffer = io.StringIO()
    if header is not None:
        meta = csv.writer(buffer)
        for label, value in _header_pairs(header):
            meta.writerow([label, value])
        meta.writerow([])

    writer = csv.DictWriter(buffer, fieldnames=_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    flat = flatten_journal_lines(hydrated_rows)
    if not flat:
        writer.writerow(
            {
                "fecha": "",
                "asiento": "",
                "cuenta": "",
                "descripción": EMPTY_PERIOD_NOTICE,
                "debe": "",
                "haber": "",
                "origen": "",
            }
        )
    else:
        for row in flat:
            writer.writerow(row)
        total_debe, total_haber = journal_totals(flat)
        writer.writerow(
            {
                "fecha": "",
                "asiento": "",
                "cuenta": "",
                "descripción": "Totales",
                "debe": str(total_debe),
                "haber": str(total_haber),
                "origen": "",
            }
        )
    return buffer.getvalue()


def _write_excel_number(sheet: Any, row: int, column: int, value: Any) -> None:
    if value in (None, ""):
        sheet.cell(row=row, column=column, value="")
        return
    try:
        sheet.cell(row=row, column=column, value=float(Decimal(str(value))))
    except Exception:
        sheet.cell(row=row, column=column, value=value)


def _format_entry_at(value: Any) -> str:
    if value is None or value == "":
        return ""
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def entries_to_xlsx(
    hydrated_rows: list[dict[str, Any]],
    *,
    header: JournalExportHeader,
) -> bytes:
    """Build a Diario workbook with header metadata, Spanish columns, and totals."""
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "Diario"

    row_idx = 1
    for label, value in _header_pairs(header):
        sheet.cell(row=row_idx, column=1, value=label)
        sheet.cell(row=row_idx, column=2, value=value)
        row_idx += 1
    row_idx += 1  # blank separator

    for col_idx, name in enumerate(_CSV_FIELDS, start=1):
        sheet.cell(row=row_idx, column=col_idx, value=name)
    header_row = row_idx
    row_idx += 1

    flat = flatten_journal_lines(hydrated_rows)
    if not flat:
        sheet.cell(row=row_idx, column=4, value=EMPTY_PERIOD_NOTICE)
        row_idx += 1
    else:
        for item in flat:
            for col_idx, key in enumerate(_CSV_FIELDS, start=1):
                value = item.get(key)
                if key in {"debe", "haber"} and value not in (None, ""):
                    _write_excel_number(sheet, row_idx, col_idx, value)
                else:
                    sheet.cell(row=row_idx, column=col_idx, value=value if value is not None else "")
            row_idx += 1
        total_debe, total_haber = journal_totals(flat)
        sheet.cell(row=row_idx, column=4, value="Totales")
        sheet.cell(row=row_idx, column=5, value=float(total_debe))
        sheet.cell(row=row_idx, column=6, value=float(total_haber))
        row_idx += 1

    # Freeze below the column header for easier scrolling.
    sheet.freeze_panes = f"A{header_row + 1}"

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def ledger_to_xlsx(
    ledger_payload: dict[str, Any],
    *,
    header: JournalExportHeader,
) -> bytes:
    """Build a Mayor workbook from general_ledger() output (running balance per account)."""
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "Mayor"

    row_idx = 1
    for label, value in _header_pairs(header):
        sheet.cell(row=row_idx, column=1, value=label)
        sheet.cell(row=row_idx, column=2, value=value)
        row_idx += 1
    row_idx += 1  # blank separator

    accounts = list(ledger_payload.get("accounts") or [])
    freeze_at: int | None = None

    if not accounts:
        for col_idx, name in enumerate(_MAYOR_FIELDS, start=1):
            sheet.cell(row=row_idx, column=col_idx, value=name)
        freeze_at = row_idx + 1
        row_idx += 1
        sheet.cell(row=row_idx, column=3, value=EMPTY_PERIOD_NOTICE)
        row_idx += 1
    else:
        for account in accounts:
            code = account.get("code") or ""
            name = account.get("name") or ""
            sheet.cell(row=row_idx, column=1, value="Cuenta")
            sheet.cell(row=row_idx, column=2, value=f"{code} {name}".strip())
            row_idx += 1
            sheet.cell(row=row_idx, column=1, value="Saldo cierre")
            _write_excel_number(sheet, row_idx, 2, account.get("closing_balance"))
            row_idx += 1

            for col_idx, field in enumerate(_MAYOR_FIELDS, start=1):
                sheet.cell(row=row_idx, column=col_idx, value=field)
            if freeze_at is None:
                freeze_at = row_idx + 1
            row_idx += 1

            lines = list(account.get("lines") or [])
            if not lines:
                sheet.cell(row=row_idx, column=3, value=EMPTY_PERIOD_NOTICE)
                row_idx += 1
            else:
                for line in lines:
                    sheet.cell(row=row_idx, column=1, value=_format_entry_at(line.get("entry_at")))
                    sheet.cell(row=row_idx, column=2, value=line.get("kind") or "")
                    sheet.cell(row=row_idx, column=3, value=line.get("memo") or "")
                    _write_excel_number(sheet, row_idx, 4, line.get("debit"))
                    _write_excel_number(sheet, row_idx, 5, line.get("credit"))
                    _write_excel_number(sheet, row_idx, 6, line.get("balance"))
                    row_idx += 1
            row_idx += 1  # blank between accounts

    if freeze_at is not None:
        sheet.freeze_panes = f"A{freeze_at}"

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _income_is_empty(statement: dict[str, Any]) -> bool:
    return all(_as_decimal(statement.get(key)) == 0 for key, _label in _INCOME_ROWS)


def income_to_xlsx(
    statement: dict[str, Any],
    *,
    header: JournalExportHeader,
) -> bytes:
    """Build a Resultado workbook matching the on-screen income statement labels."""
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "Resultado"

    row_idx = 1
    for label, value in _header_pairs(header):
        sheet.cell(row=row_idx, column=1, value=label)
        sheet.cell(row=row_idx, column=2, value=value)
        row_idx += 1
    row_idx += 1  # blank separator

    sheet.cell(row=row_idx, column=1, value="concepto")
    sheet.cell(row=row_idx, column=2, value="monto")
    header_row = row_idx
    row_idx += 1

    if _income_is_empty(statement):
        sheet.cell(row=row_idx, column=1, value=EMPTY_PERIOD_NOTICE)
        row_idx += 1
    else:
        currency = str(statement.get("currency") or "BOB")
        for key, label in _INCOME_ROWS:
            sheet.cell(row=row_idx, column=1, value=label)
            _write_excel_number(sheet, row_idx, 2, statement.get(key))
            row_idx += 1
        sheet.cell(row=row_idx, column=1, value="Moneda")
        sheet.cell(row=row_idx, column=2, value=currency)
        row_idx += 1
        note = statement.get("note") or ""
        if note:
            sheet.cell(row=row_idx, column=1, value="Nota")
            sheet.cell(row=row_idx, column=2, value=str(note))
            row_idx += 1

    sheet.freeze_panes = f"A{header_row + 1}"

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _render_simple_pdf(lines: list[str]) -> bytes:
    """Minimal single-page PDF (Helvetica, no deps)."""
    content_lines = ["BT", "/F1 9 Tf", "40 760 Td", "12 TL"]
    for index, line in enumerate(lines[:55]):
        escaped = _pdf_escape(line[:110])
        if index == 0:
            content_lines.append(f"({escaped}) Tj")
        else:
            content_lines.append("T*")
            content_lines.append(f"({escaped}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n".encode("ascii"))
        out.extend(obj if isinstance(obj, bytes) else obj)
        out.extend(b"\nendobj\n")
    xref_at = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)


def income_to_pdf(
    statement: dict[str, Any],
    *,
    header: JournalExportHeader,
) -> bytes:
    """Minimal Resultado PDF with header metadata and managerial footer legend."""
    lines = [
        f"{header.report_type} - {header.business_name}",
        f"Periodo: {header.period_label}",
        f"Generado: {header.generated_at}",
        f"Actor: {header.actor_name}",
        "concepto | monto",
    ]
    if _income_is_empty(statement):
        lines.append(EMPTY_PERIOD_NOTICE)
    else:
        currency = str(statement.get("currency") or "BOB")
        for key, label in _INCOME_ROWS:
            amount = statement.get(key)
            lines.append(f"{label} | {amount} {currency}".strip())
        note = statement.get("note") or ""
        if note:
            lines.append(str(note))
    lines.append(FINANCIAL_PDF_FOOTER)
    return _render_simple_pdf(lines)


def _balance_is_empty(sheet: dict[str, Any]) -> bool:
    rows = sheet.get("rows") or []
    if rows:
        return False
    return all(_as_decimal(sheet.get(key)) == 0 for key, _label in _BALANCE_SUMMARY_ROWS)


def _balance_cuadra_label(sheet: dict[str, Any]) -> str:
    return "Sí" if bool(sheet.get("balanced_check")) else "No"


def balance_to_xlsx(
    sheet_data: dict[str, Any],
    *,
    header: JournalExportHeader,
) -> bytes:
    """Build a Balance general workbook matching the on-screen balance sheet labels."""
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "Balance"

    row_idx = 1
    for label, value in _header_pairs(header):
        sheet.cell(row=row_idx, column=1, value=label)
        sheet.cell(row=row_idx, column=2, value=value)
        row_idx += 1
    row_idx += 1  # blank separator

    sheet.cell(row=row_idx, column=1, value="concepto")
    sheet.cell(row=row_idx, column=2, value="monto")
    header_row = row_idx
    row_idx += 1

    if _balance_is_empty(sheet_data):
        sheet.cell(row=row_idx, column=1, value=EMPTY_PERIOD_NOTICE)
        row_idx += 1
    else:
        for key, label in _BALANCE_SUMMARY_ROWS:
            sheet.cell(row=row_idx, column=1, value=label)
            _write_excel_number(sheet, row_idx, 2, sheet_data.get(key))
            row_idx += 1
        sheet.cell(row=row_idx, column=1, value="Cuadra")
        sheet.cell(row=row_idx, column=2, value=_balance_cuadra_label(sheet_data))
        row_idx += 2  # blank before detail table

        for col_idx, name in enumerate(_BALANCE_FIELDS, start=1):
            sheet.cell(row=row_idx, column=col_idx, value=name)
        row_idx += 1

        for item in sheet_data.get("rows") or []:
            account_type = str(item.get("account_type") or "")
            tipo = _BALANCE_TYPE_LABEL.get(account_type, account_type)
            sheet.cell(row=row_idx, column=1, value=str(item.get("code") or ""))
            sheet.cell(row=row_idx, column=2, value=str(item.get("name") or ""))
            sheet.cell(row=row_idx, column=3, value=tipo)
            _write_excel_number(sheet, row_idx, 4, item.get("balance"))
            row_idx += 1

    sheet.freeze_panes = f"A{header_row + 1}"

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def balance_to_pdf(
    sheet_data: dict[str, Any],
    *,
    header: JournalExportHeader,
) -> bytes:
    """Minimal Balance PDF with header metadata, cuadra, and managerial footer legend."""
    lines = [
        f"{header.report_type} - {header.business_name}",
        f"Periodo: {header.period_label}",
        f"Generado: {header.generated_at}",
        f"Actor: {header.actor_name}",
        "concepto | monto",
    ]
    if _balance_is_empty(sheet_data):
        lines.append(EMPTY_PERIOD_NOTICE)
    else:
        for key, label in _BALANCE_SUMMARY_ROWS:
            amount = sheet_data.get(key)
            lines.append(f"{label} | {amount}")
        lines.append(f"Cuadra | {_balance_cuadra_label(sheet_data)}")
        lines.append("codigo | cuenta | tipo | saldo")
        for item in sheet_data.get("rows") or []:
            account_type = str(item.get("account_type") or "")
            tipo = _BALANCE_TYPE_LABEL.get(account_type, account_type)
            lines.append(
                " | ".join(
                    [
                        str(item.get("code") or "")[:16],
                        str(item.get("name") or "")[:28],
                        tipo[:16],
                        str(item.get("balance") or ""),
                    ]
                )
            )
    lines.append(FINANCIAL_PDF_FOOTER)
    return _render_simple_pdf(lines)


def _trial_cuadra_label(payload: dict[str, Any]) -> str:
    return "Sí" if bool(payload.get("balanced")) else "No"


def _match_label(value: Any) -> str:
    return "Sí" if bool(value) else "No"


def _write_export_header_block(sheet: Any, header: JournalExportHeader) -> int:
    """Write Negocio/Tipo/Período/… block; return next free 1-based row index."""
    row_idx = 1
    for label, value in _header_pairs(header):
        sheet.cell(row=row_idx, column=1, value=label)
        sheet.cell(row=row_idx, column=2, value=value)
        row_idx += 1
    row_idx += 1  # blank separator
    return row_idx


def trial_balance_to_xlsx(
    payload: dict[str, Any],
    *,
    header: JournalExportHeader,
) -> bytes:
    """Build a Comprobación workbook from trial_balance() output (Spanish columns)."""
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "Comprobación"

    row_idx = _write_export_header_block(sheet, header)

    for col_idx, name in enumerate(_TRIAL_FIELDS, start=1):
        sheet.cell(row=row_idx, column=col_idx, value=name)
    header_row = row_idx
    row_idx += 1

    rows = list(payload.get("rows") or [])
    if not rows:
        sheet.cell(row=row_idx, column=2, value=EMPTY_PERIOD_NOTICE)
        row_idx += 1
    else:
        for item in rows:
            sheet.cell(row=row_idx, column=1, value=str(item.get("code") or ""))
            sheet.cell(row=row_idx, column=2, value=str(item.get("name") or ""))
            _write_excel_number(sheet, row_idx, 3, item.get("debit"))
            _write_excel_number(sheet, row_idx, 4, item.get("credit"))
            row_idx += 1
        sheet.cell(row=row_idx, column=2, value="Totales")
        _write_excel_number(sheet, row_idx, 3, payload.get("total_debit"))
        _write_excel_number(sheet, row_idx, 4, payload.get("total_credit"))
        row_idx += 1
        sheet.cell(row=row_idx, column=1, value="Cuadra")
        sheet.cell(row=row_idx, column=2, value=_trial_cuadra_label(payload))
        row_idx += 1

    sheet.freeze_panes = f"A{header_row + 1}"

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def bank_recon_to_xlsx(
    payload: dict[str, Any],
    *,
    header: JournalExportHeader,
) -> bytes:
    """Build a Conciliación workbook from bank_recon_suggest() output (Spanish sheets)."""
    from openpyxl import Workbook

    book = Workbook()
    banco = book.active
    banco.title = "Banco"
    pagos = book.create_sheet("Pagos")
    matches_sheet = book.create_sheet("Matches")

    bank_lines = list(payload.get("bank_lines") or [])
    payments = list(payload.get("payments") or [])
    matches = list(payload.get("matches") or [])
    empty = not bank_lines and not payments and not matches

    # --- Banco ---
    row_idx = _write_export_header_block(banco, header)
    for col_idx, name in enumerate(_RECON_BANCO_FIELDS, start=1):
        banco.cell(row=row_idx, column=col_idx, value=name)
    banco_header_row = row_idx
    row_idx += 1
    if empty:
        banco.cell(row=row_idx, column=1, value=EMPTY_PERIOD_NOTICE)
    elif not bank_lines:
        banco.cell(row=row_idx, column=1, value=EMPTY_PERIOD_NOTICE)
    else:
        for item in bank_lines:
            banco.cell(row=row_idx, column=1, value=_format_entry_at(item.get("entry_at")))
            banco.cell(row=row_idx, column=2, value=str(item.get("direction") or ""))
            _write_excel_number(banco, row_idx, 3, item.get("amount"))
            banco.cell(row=row_idx, column=4, value=str(item.get("memo") or ""))
            banco.cell(row=row_idx, column=5, value=_match_label(item.get("matched")))
            row_idx += 1
    banco.freeze_panes = f"A{banco_header_row + 1}"

    # --- Pagos ---
    row_idx = _write_export_header_block(pagos, header)
    for col_idx, name in enumerate(_RECON_PAGO_FIELDS, start=1):
        pagos.cell(row=row_idx, column=col_idx, value=name)
    pagos_header_row = row_idx
    row_idx += 1
    if empty or not payments:
        pagos.cell(row=row_idx, column=1, value=EMPTY_PERIOD_NOTICE)
    else:
        for item in payments:
            pagos.cell(row=row_idx, column=1, value=_format_entry_at(item.get("created_at")))
            pagos.cell(row=row_idx, column=2, value=str(item.get("provider") or ""))
            _write_excel_number(pagos, row_idx, 3, item.get("amount"))
            pagos.cell(row=row_idx, column=4, value=_match_label(item.get("matched")))
            row_idx += 1
    pagos.freeze_panes = f"A{pagos_header_row + 1}"

    # --- Matches ---
    row_idx = _write_export_header_block(matches_sheet, header)
    for col_idx, name in enumerate(_RECON_MATCH_FIELDS, start=1):
        matches_sheet.cell(row=row_idx, column=col_idx, value=name)
    matches_header_row = row_idx
    row_idx += 1
    if empty or not matches:
        matches_sheet.cell(row=row_idx, column=1, value=EMPTY_PERIOD_NOTICE)
    else:
        for item in matches:
            matches_sheet.cell(row=row_idx, column=1, value=str(item.get("entry_id") or ""))
            matches_sheet.cell(row=row_idx, column=2, value=str(item.get("payment_id") or ""))
            _write_excel_number(matches_sheet, row_idx, 3, item.get("amount"))
            matches_sheet.cell(row=row_idx, column=4, value=str(item.get("day") or ""))
            row_idx += 1
    matches_sheet.freeze_panes = f"A{matches_header_row + 1}"

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def entries_to_pdf(
    hydrated_rows: list[dict[str, Any]],
    *,
    period_label: str,
    header: JournalExportHeader | None = None,
) -> bytes:
    """Minimal single-page PDF for journal rows (Helvetica, no deps)."""
    lines = [
        "Diario - export",
        f"Periodo: {period_label}",
    ]
    if header is not None:
        lines = [
            f"{header.report_type} - {header.business_name}",
            f"Periodo: {header.period_label}",
            f"Generado: {header.generated_at}",
            f"Actor: {header.actor_name}",
        ]
    lines.append("fecha | asiento | cuenta | descripcion | debe | haber | origen")
    flat = flatten_journal_lines(hydrated_rows)
    if not flat:
        lines.append(EMPTY_PERIOD_NOTICE)
    else:
        for row in flat:
            lines.append(
                " | ".join(
                    [
                        str(row.get("fecha") or "")[:19],
                        str(row.get("asiento") or "")[:8],
                        str(row.get("cuenta") or "")[:24],
                        str(row.get("descripción") or "")[:24],
                        str(row.get("debe") or ""),
                        str(row.get("haber") or ""),
                        str(row.get("origen") or "")[:20],
                    ]
                )
            )
        total_debe, total_haber = journal_totals(flat)
        lines.append(f"Totales debe={total_debe} haber={total_haber}")

    return _render_simple_pdf(lines)
