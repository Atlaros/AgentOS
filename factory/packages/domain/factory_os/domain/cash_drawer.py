"""Cash drawer sessions: open/close and movement gating (ADR-009 T1)."""

from __future__ import annotations

import csv
import io
from datetime import UTC, date
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from uuid import UUID

from factory_os.domain.models import CashMovement, CashSaleTicket, CashSession


class CashSessionStore(Protocol):
    def get_open_cash_session(self, tenant_id: UUID) -> CashSession | None: ...
    def list_cash_sessions(self, tenant_id: UUID, *, status: str | None = None) -> list[CashSession]: ...
    def open_cash_session(
        self,
        tenant_id: UUID,
        opening_float: Decimal,
        currency: str,
        opened_by_name: str,
        opened_by_id: UUID | None = None,
    ) -> CashSession: ...
    def close_cash_session(
        self,
        tenant_id: UUID,
        *,
        counted_cash: Decimal,
        expected_cash: Decimal,
        difference: Decimal,
        note: str,
        closed_by_name: str,
        closed_by_id: UUID | None = None,
    ) -> CashSession: ...
    def reopen_cash_session(
        self,
        tenant_id: UUID,
        *,
        reopened_by_name: str,
        reopened_by_id: UUID | None = None,
    ) -> CashSession: ...
    def list_cash(self, tenant_id: UUID, session_id: UUID | None = None) -> list[CashMovement]: ...
    def list_cash_sale_tickets(
        self, tenant_id: UUID, session_id: UUID | None = None
    ) -> list[CashSaleTicket]: ...


def format_money(amount: Decimal) -> str:
    return f"{Decimal(amount).quantize(Decimal('0.01')):.2f}"


def parse_money(raw: object) -> Decimal:
    try:
        text = str(raw).strip().replace(",", ".")
        amount = Decimal(text)
    except (InvalidOperation, AttributeError, TypeError) as exc:
        raise ValueError("bad_amount") from exc
    if amount < 0:
        raise ValueError("bad_amount")
    return amount.quantize(Decimal("0.01"))


def sum_session_cash(movements: list[CashMovement]) -> tuple[Decimal, Decimal]:
    """Sum in/out for arqueo; soft-voided rows are excluded from totals."""
    active = [item for item in movements if item.status != "voided"]
    cash_in = sum((item.amount for item in active if item.direction == "in"), Decimal("0"))
    cash_out = sum((item.amount for item in active if item.direction == "out"), Decimal("0"))
    return cash_in, cash_out


def _parse_iso_date(raw: str | None) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _movement_date_utc(movement: CashMovement) -> date | None:
    created = movement.created_at
    if created is None:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return created.astimezone(UTC).date()


def filter_movements(
    movements: list[CashMovement],
    *,
    direction: str | None = None,
    category: str | None = None,
    method: str | None = None,
    status: str | None = None,
    user: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[CashMovement]:
    """Filter cash movements in memory (UTC calendar dates inclusive)."""
    direction_norm = (direction or "").strip().lower() or None
    category_norm = (category or "").strip().lower() or None
    method_norm = (method or "").strip().lower() or None
    status_norm = (status or "").strip().lower() or None
    user_norm = (user or "").strip().lower() or None
    start = _parse_iso_date(from_date)
    end = _parse_iso_date(to_date)

    filtered: list[CashMovement] = []
    for item in movements:
        if direction_norm and (item.direction or "").strip().lower() != direction_norm:
            continue
        if category_norm and (item.category or "").strip().lower() != category_norm:
            continue
        if method_norm and (item.method or "cash").strip().lower() != method_norm:
            continue
        if status_norm and (item.status or "recorded").strip().lower() != status_norm:
            continue
        if user_norm and user_norm not in (item.recorded_by_name or "").lower():
            continue
        if start is not None or end is not None:
            day = _movement_date_utc(item)
            if day is None:
                continue
            if start is not None and day < start:
                continue
            if end is not None and day > end:
                continue
        filtered.append(item)
    return filtered


_CSV_FIELDS = (
    "direction",
    "amount",
    "currency",
    "category",
    "method",
    "status",
    "reason",
    "recorded_by_name",
    "created_at",
    "ticket_id",
)


def movements_to_csv(movements: list[CashMovement]) -> str:
    """Serialize filtered movements as UTF-8 CSV text."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for item in movements:
        payload = movement_payload(item)
        writer.writerow({key: payload.get(key) or "" for key in _CSV_FIELDS})
    return buffer.getvalue()


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def movements_to_pdf(movements: list[CashMovement]) -> bytes:
    """Minimal single-page PDF listing filtered cash rows (Helvetica, no deps)."""
    lines = [
        "Caja - export",
        "direction | amount | currency | category | method | status | reason | user | created_at",
    ]
    for item in movements:
        created = item.created_at.isoformat() if item.created_at else ""
        lines.append(
            " | ".join(
                [
                    item.direction or "",
                    str(item.amount),
                    item.currency or "",
                    item.category or "",
                    item.method or "cash",
                    item.status or "recorded",
                    (item.reason or "").replace("\n", " ")[:60],
                    (item.recorded_by_name or "")[:24],
                    created,
                ]
            )
        )
    if len(lines) == 2:
        lines.append("(sin movimientos)")

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


def movement_payload(movement: CashMovement) -> dict[str, Any]:
    """Serialize a cash movement for panel API responses."""
    return {
        "id": str(movement.id),
        "direction": movement.direction,
        "amount": str(movement.amount),
        "currency": movement.currency,
        "reason": movement.reason,
        "category": movement.category or "",
        "method": movement.method or "cash",
        "status": movement.status or "recorded",
        "recorded_by_name": movement.recorded_by_name or "",
        "recorded_by_id": str(movement.recorded_by_id) if movement.recorded_by_id else None,
        "created_at": movement.created_at.isoformat() if movement.created_at else None,
        "session_id": str(movement.session_id) if movement.session_id else None,
        "void_reason": movement.void_reason,
        "voided_by_name": movement.voided_by_name,
        "voided_by_id": str(movement.voided_by_id) if movement.voided_by_id else None,
        "voided_at": movement.voided_at.isoformat() if movement.voided_at else None,
        "ticket_id": str(movement.ticket_id) if movement.ticket_id else None,
    }


def expected_cash(opening_float: Decimal, cash_in: Decimal, cash_out: Decimal) -> Decimal:
    return (opening_float + cash_in - cash_out).quantize(Decimal("0.01"))


def session_payload(store: CashSessionStore, session: CashSession) -> dict[str, Any]:
    """Serialize a session; open sessions get live in/out/expected from movements."""
    from factory_os.domain.cash_sales import sum_session_qr_in

    tickets = store.list_cash_sale_tickets(session.tenant_id, session_id=session.id)
    qr_in = format_money(sum_session_qr_in(tickets))
    if session.status == "open":
        movements = store.list_cash(session.tenant_id, session_id=session.id)
        cash_in, cash_out = sum_session_cash(movements)
        expected = expected_cash(session.opening_float, cash_in, cash_out)
        return {
            "id": str(session.id),
            "status": "open",
            "opening_float": format_money(session.opening_float),
            "in": format_money(cash_in),
            "out": format_money(cash_out),
            "expected_cash": format_money(expected),
            "qr_in": qr_in,
            "opened_at": session.opened_at.isoformat() if session.opened_at else None,
            "opened_by_name": session.opened_by_name,
        }
    return {
        "id": str(session.id),
        "status": "closed",
        "opening_float": format_money(session.opening_float),
        "counted_cash": format_money(session.counted_cash or Decimal("0")),
        "expected_cash": format_money(session.expected_cash or Decimal("0")),
        "difference": format_money(session.difference or Decimal("0")),
        "qr_in": qr_in,
        "close_note": session.close_note or "",
        "opened_at": session.opened_at.isoformat() if session.opened_at else None,
        "opened_by_name": session.opened_by_name,
        "closed_at": session.closed_at.isoformat() if session.closed_at else None,
        "closed_by_name": session.closed_by_name,
    }


def open_session(
    store: CashSessionStore,
    tenant_id: UUID,
    opening_float: Decimal,
    currency: str,
    opened_by_name: str,
    opened_by_id: UUID | None = None,
) -> CashSession:
    if opening_float < 0:
        raise ValueError("bad_amount")
    if store.get_open_cash_session(tenant_id) is not None:
        raise ValueError("session_open")
    return store.open_cash_session(
        tenant_id,
        opening_float.quantize(Decimal("0.01")),
        currency or "BOB",
        opened_by_name,
        opened_by_id,
    )


def close_session(
    store: CashSessionStore,
    tenant_id: UUID,
    counted_cash: Decimal,
    note: str,
    closed_by_name: str,
    closed_by_id: UUID | None = None,
) -> CashSession:
    if counted_cash < 0:
        raise ValueError("bad_amount")
    session = store.get_open_cash_session(tenant_id)
    if session is None:
        raise ValueError("session_required")
    movements = store.list_cash(tenant_id, session_id=session.id)
    cash_in, cash_out = sum_session_cash(movements)
    expected = expected_cash(session.opening_float, cash_in, cash_out)
    counted = counted_cash.quantize(Decimal("0.01"))
    difference = (counted - expected).quantize(Decimal("0.01"))
    note_clean = (note or "").strip()
    if difference != 0 and not note_clean:
        raise ValueError("note_required")
    return store.close_cash_session(
        tenant_id,
        counted_cash=counted,
        expected_cash=expected,
        difference=difference,
        note=note_clean,
        closed_by_name=closed_by_name,
        closed_by_id=closed_by_id,
    )


def ensure_open_session(
    store: CashSessionStore,
    tenant_id: UUID,
    *,
    currency: str = "BOB",
    opened_by_name: str = "sistema",
) -> CashSession:
    """Auto-open with float 0 for settle_cash / staff tools when no session exists."""
    existing = store.get_open_cash_session(tenant_id)
    if existing is not None:
        return existing
    return store.open_cash_session(tenant_id, Decimal("0.00"), currency or "BOB", opened_by_name, None)


def reopen_session(
    store: CashSessionStore,
    tenant_id: UUID,
    reopened_by_name: str,
    reopened_by_id: UUID | None = None,
) -> CashSession:
    """Reopen the latest closed session for the tenant (same id)."""
    if store.get_open_cash_session(tenant_id) is not None:
        raise ValueError("session_open")
    return store.reopen_cash_session(
        tenant_id,
        reopened_by_name=reopened_by_name,
        reopened_by_id=reopened_by_id,
    )
