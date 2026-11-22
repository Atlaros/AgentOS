"""Commercial walk-in sale receipt PDF (no external PDF deps, not a fiscal invoice)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

# Readable receipt width (~106mm), not a letter-size journal.
_PAGE_WIDTH = 300.0
_LEFT = 16.0
_RIGHT = 284.0
_TOP_MARGIN = 20.0
_BOTTOM_MARGIN = 18.0
_NAME_X = 46.0
_UNIT_RIGHT = 224.0
_TOTAL_RIGHT = _RIGHT

_STATUS_LABEL = {
    "recorded": "Confirmado",
    "voided": "Anulado",
    "pending_qr": "Pendiente QR",
}

_METHOD_LABEL = {
    "cash": "Efectivo",
    "qr": "QR",
}

# Helvetica AFM widths (1000-unit em). Digits stay even so amounts line up.
_CHAR_UNITS = {
    " ": 278,
    ".": 278,
    ",": 278,
    ":": 278,
    ";": 278,
    "-": 333,
    "/": 278,
    "(": 333,
    ")": 333,
    "[": 278,
    "]": 278,
    "N": 722,
    "º": 400,
}
for _digit in "0123456789":
    _CHAR_UNITS[_digit] = 556


@dataclass(frozen=True)
class _TextRow:
    text: str
    size: float = 9.0
    bold: bool = False
    align: str = "left"
    gap: float = 3.0


@dataclass(frozen=True)
class _Rule:
    gap: float = 6.0


@dataclass(frozen=True)
class _Columns:
    qty: str
    name: str
    unit: str
    total: str
    bold: bool = False
    size: float = 8.5
    gap: float = 3.0


_Block = _TextRow | _Rule | _Columns


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _ascii_safe(text: str) -> str:
    """Normalize to Helvetica WinAnsi / latin-1."""
    return (text or "").encode("latin-1", errors="replace").decode("latin-1")


def _business_name() -> str:
    return (
        (os.environ.get("CASH_TICKET_BUSINESS_NAME") or "").strip()
        or (os.environ.get("SHOP_NAME") or "").strip()
        or "Del Campus Café"
    )


def _format_when(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat(sep=" ", timespec="minutes")
        except TypeError:
            return value.isoformat()
    text = str(value).strip()
    if not text:
        return ""
    return text.replace("T", " ")[:16]


def _text_width(text: str, size: float) -> float:
    units = 0
    for char in text:
        if char in _CHAR_UNITS:
            units += _CHAR_UNITS[char]
        elif char.isupper():
            units += 680
        else:
            units += 500
    return units * size / 1000.0


def _fit(text: str, size: float, max_width: float) -> str:
    if _text_width(text, size) <= max_width:
        return text
    ellipsis = "..."
    trimmed = text
    while trimmed and _text_width(trimmed + ellipsis, size) > max_width:
        trimmed = trimmed[:-1]
    return f"{trimmed}{ellipsis}" if trimmed else ellipsis


def _item_label(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip() or "producto"
    sku = str(item.get("variant_sku") or "").strip()
    attrs = " / ".join(
        part
        for part in (
            str(item.get("talla") or "").strip(),
            str(item.get("color") or "").strip(),
        )
        if part
    )
    label = name
    if sku:
        label = f"{label} ({sku})"
    if attrs:
        label = f"{label} [{attrs}]"
    return label


def _receipt_blocks(detail: dict[str, Any]) -> list[_Block]:
    method = str(detail.get("method") or "cash").strip().lower() or "cash"
    status = str(detail.get("status") or "recorded").strip().lower() or "recorded"
    ticket_number = str(detail.get("ticket_number") or "").strip()
    currency = str(detail.get("currency") or "BOB").strip() or "BOB"
    amount = str(detail.get("amount") or "").strip()
    attended = str(detail.get("recorded_by_name") or "").strip() or "sistema"
    when = _format_when(detail.get("created_at"))

    blocks: list[_Block] = [
        _TextRow(_business_name(), size=13, bold=True, align="center", gap=2),
        _TextRow("COMPROBANTE DE VENTA", size=11, bold=True, align="center", gap=2),
        _TextRow("No es factura fiscal", size=8, align="center", gap=4),
        _Rule(),
        _TextRow(f"Ticket Nº: {ticket_number}" if ticket_number else "Ticket Nº: —"),
        _TextRow(f"Fecha: {when}" if when else "Fecha: —"),
        _TextRow(f"Atendido por: {attended}"),
        _TextRow(f"Método: {_METHOD_LABEL.get(method, method)}"),
        _TextRow(f"Estado: {_STATUS_LABEL.get(status, status)}", gap=4),
        _Rule(),
        _Columns("Cant.", "Producto", "P.unit", "Importe", bold=True, size=8, gap=4),
    ]

    raw_lines = detail.get("lines") or []
    drew_item = False
    if isinstance(raw_lines, list):
        for item in raw_lines:
            if not isinstance(item, dict):
                continue
            qty = int(item.get("quantity") or 1)
            unit = str(item.get("unit_price") or "").strip()
            line_total = str(item.get("line_total") or "").strip()
            blocks.append(
                _Columns(
                    str(qty),
                    _item_label(item),
                    unit or "—",
                    line_total or "—",
                )
            )
            drew_item = True
    if not drew_item:
        blocks.append(_TextRow("(sin líneas)", size=8.5))

    blocks.append(_Rule(gap=5))
    total_label = f"TOTAL  {amount} {currency}".strip()
    blocks.append(_TextRow(total_label, size=13, bold=True, align="right", gap=4))

    tendered = detail.get("tendered")
    change = detail.get("change")
    if method == "cash" and tendered not in (None, ""):
        blocks.append(_TextRow(f"Entregado: {tendered} {currency}".strip(), align="right", gap=1))
        if change not in (None, ""):
            blocks.append(_TextRow(f"Vuelto: {change} {currency}".strip(), align="right", gap=3))

    blocks.extend(
        [
            _Rule(),
            _TextRow("Gracias por su compra", size=9, align="center", gap=2),
            _TextRow("No es factura fiscal", size=8, align="center", gap=0),
        ]
    )
    return blocks


def _build_receipt_lines(detail: dict[str, Any]) -> list[str]:
    """Flat latin-1 lines used by tests and as the receipt's readable content."""
    lines: list[str] = []
    for block in _receipt_blocks(detail):
        if isinstance(block, _TextRow):
            lines.append(_ascii_safe(block.text))
        elif isinstance(block, _Columns):
            lines.append(
                _ascii_safe(f"{block.qty}  {block.name}  {block.unit}  {block.total}")
            )
    return lines


def _block_height(block: _Block) -> float:
    if isinstance(block, _Rule):
        return block.gap + 4.0
    return block.size + block.gap + 2.0


def _place_x(text: str, size: float, align: str) -> float:
    width = _text_width(text, size)
    if align == "center":
        return max(_LEFT, (_PAGE_WIDTH - width) / 2.0)
    if align == "right":
        return max(_LEFT, _RIGHT - width)
    return _LEFT


def _text_ops(text: str, x: float, baseline: float, size: float, bold: bool) -> list[str]:
    font = "F2" if bold else "F1"
    escaped = _pdf_escape(_ascii_safe(text))
    return [
        "BT",
        f"/{font} {size:.1f} Tf",
        f"1 0 0 1 {x:.2f} {baseline:.2f} Tm",
        f"({escaped}) Tj",
        "ET",
    ]


def _column_ops(block: _Columns, baseline: float) -> list[str]:
    name_max = _UNIT_RIGHT - 48.0 - _NAME_X
    name = _fit(block.name, block.size, name_max)
    ops = _text_ops(block.qty, _LEFT, baseline, block.size, block.bold)
    ops.extend(_text_ops(name, _NAME_X, baseline, block.size, block.bold))
    unit_x = _UNIT_RIGHT - _text_width(block.unit, block.size)
    total_x = _TOTAL_RIGHT - _text_width(block.total, block.size)
    ops.extend(_text_ops(block.unit, unit_x, baseline, block.size, block.bold))
    ops.extend(_text_ops(block.total, total_x, baseline, block.size, block.bold))
    return ops


def _content_stream(blocks: list[_Block], page_height: float) -> bytes:
    cursor = page_height - _TOP_MARGIN
    ops: list[str] = ["0.6 w", "0.15 0.15 0.15 RG"]
    for block in blocks:
        if isinstance(block, _Rule):
            y = cursor - 2.0
            ops.append(f"{_LEFT:.2f} {y:.2f} m {_RIGHT:.2f} {y:.2f} l S")
            cursor -= _block_height(block)
            continue
        baseline = cursor - block.size
        if isinstance(block, _Columns):
            ops.extend(_column_ops(block, baseline))
        else:
            ops.extend(
                _text_ops(
                    block.text,
                    _place_x(block.text, block.size, block.align),
                    baseline,
                    block.size,
                    block.bold,
                )
            )
        cursor -= _block_height(block)
    return "\n".join(ops).encode("latin-1", errors="replace")


def sale_ticket_to_pdf(detail: dict[str, Any]) -> bytes:
    """Build a commercial sale receipt PDF from an activity detail dict."""
    blocks = _receipt_blocks(detail)
    page_height = max(
        420.0,
        _TOP_MARGIN + _BOTTOM_MARGIN + sum(_block_height(block) for block in blocks),
    )
    stream = _content_stream(blocks, page_height)
    page_obj = (
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_WIDTH:.1f} {page_height:.1f}] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>"
    ).encode("ascii")
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        page_obj,
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    return _assemble_pdf(objects)


def _assemble_pdf(objects: list[bytes]) -> bytes:
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref_at = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(out)
