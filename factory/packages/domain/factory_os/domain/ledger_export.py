"""CSV/PDF/XLSX export and source breakdown for Contabilidad (ADR-010 / ADR-011)."""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from typing import Any

from factory_os.domain.ledger import sum_ledger
from factory_os.domain.models import LedgerEntry

_SOURCES = ("payment", "cash", "purchase")

_CSV_FIELDS = (
    "created_at",
    "source",
    "source_id",
    "reference_label",
    "category",
    "method",
    "direction",
    "amount",
    "currency",
    "status",
)


def breakdown_by_source(entries: list[LedgerEntry]) -> dict[str, dict[str, str]]:
    """Recorded-only in/out/balance per source. Always returns payment/cash/purchase."""
    result: dict[str, dict[str, str]] = {}
    for source in _SOURCES:
        slice_rows = [entry for entry in entries if entry.source == source]
        incoming, outgoing, balance = sum_ledger(slice_rows)
        result[source] = {
            "in": str(incoming),
            "out": str(outgoing),
            "balance": str(balance),
        }
    return result


def entries_to_csv(hydrated_rows: list[dict[str, Any]]) -> str:
    """Serialize hydrated ledger rows as UTF-8 CSV text."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in hydrated_rows:
        writer.writerow({key: row.get(key) if row.get(key) is not None else "" for key in _CSV_FIELDS})
    return buffer.getvalue()


def hechos_to_xlsx(
    hydrated_rows: list[dict[str, Any]],
    *,
    header: Any,
) -> bytes:
    """Build a Hechos workbook from the same hydrated ledger rows as CSV export."""
    from openpyxl import Workbook

    from factory_os.domain.journal_export import EMPTY_PERIOD_NOTICE

    book = Workbook()
    sheet = book.active
    sheet.title = "Hechos"

    closed = "Sí" if getattr(header, "period_closed", False) else "No"
    meta = (
        ("Negocio", getattr(header, "business_name", "")),
        ("Tipo de reporte", getattr(header, "report_type", "Hechos")),
        ("Período", getattr(header, "period_label", "")),
        ("Generado", getattr(header, "generated_at", "")),
        ("Actor", getattr(header, "actor_name", "")),
        ("Período cerrado", closed),
    )
    row_idx = 1
    for label, value in meta:
        sheet.cell(row=row_idx, column=1, value=label)
        sheet.cell(row=row_idx, column=2, value=value)
        row_idx += 1
    row_idx += 1  # blank separator

    for col_idx, name in enumerate(_CSV_FIELDS, start=1):
        sheet.cell(row=row_idx, column=col_idx, value=name)
    header_row = row_idx
    row_idx += 1

    if not hydrated_rows:
        sheet.cell(row=row_idx, column=1, value=EMPTY_PERIOD_NOTICE)
        row_idx += 1
    else:
        for item in hydrated_rows:
            for col_idx, key in enumerate(_CSV_FIELDS, start=1):
                value = item.get(key)
                if key == "amount" and value not in (None, ""):
                    try:
                        sheet.cell(row=row_idx, column=col_idx, value=float(Decimal(str(value))))
                    except Exception:
                        sheet.cell(row=row_idx, column=col_idx, value=value)
                else:
                    sheet.cell(
                        row=row_idx,
                        column=col_idx,
                        value="" if value is None else value,
                    )
            row_idx += 1

    sheet.freeze_panes = f"A{header_row + 1}"
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def entries_to_pdf(
    hydrated_rows: list[dict[str, Any]],
    *,
    period_label: str,
    totals: dict[str, str],
    breakdown: dict[str, dict[str, str]],
) -> bytes:
    """Minimal single-page PDF for filtered ledger rows (Helvetica, no deps)."""
    lines = [
        "Contabilidad - export",
        f"Periodo: {period_label}",
        (
            f"Totales in={totals.get('in', '0')} out={totals.get('out', '0')} "
            f"balance={totals.get('balance', '0')}"
        ),
        (
            "Desglose "
            f"payment={breakdown.get('payment', {}).get('balance', '0')} "
            f"cash={breakdown.get('cash', {}).get('balance', '0')} "
            f"purchase={breakdown.get('purchase', {}).get('balance', '0')}"
        ),
        "created_at | source | reference | category | method | direction | amount | status",
    ]
    for row in hydrated_rows:
        lines.append(
            " | ".join(
                [
                    str(row.get("created_at") or "")[:19],
                    str(row.get("source") or ""),
                    str(row.get("reference_label") or row.get("source_id") or "")[:24],
                    str(row.get("category") or ""),
                    str(row.get("method") or ""),
                    str(row.get("direction") or ""),
                    f"{row.get('amount') or ''} {row.get('currency') or ''}".strip(),
                    str(row.get("status") or "recorded"),
                ]
            )
        )
    if len(hydrated_rows) == 0:
        lines.append("(sin asientos)")

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
