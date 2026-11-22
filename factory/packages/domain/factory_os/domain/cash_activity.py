"""Unified cash-session activity feed (movements + walk-in QR tickets)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Protocol
from uuid import UUID

from factory_os.domain.cash_drawer import format_money
from factory_os.domain.models import CashMovement, CashSaleLine, CashSaleTicket, CashSession

_SUMMARY_MAX = 72


class CashActivityStore(Protocol):
    def get_open_cash_session(self, tenant_id: UUID) -> CashSession | None: ...
    def list_cash_sessions(self, tenant_id: UUID, *, status: str | None = None) -> list[CashSession]: ...
    def list_cash(self, tenant_id: UUID, session_id: UUID | None = None) -> list[CashMovement]: ...
    def list_cash_sale_tickets(
        self, tenant_id: UUID, session_id: UUID | None = None
    ) -> list[CashSaleTicket]: ...


def ticket_line_summary(lines: list[CashSaleLine] | list[Any], *, max_len: int = _SUMMARY_MAX) -> str:
    """Human short line summary, e.g. ``1 prenda: Blusa…`` or ``2 prendas: blusa …``."""
    if not lines:
        return ""
    total_qty = 0
    first_name = ""
    for index, line in enumerate(lines):
        qty = int(getattr(line, "quantity", 1) or 1)
        total_qty += max(qty, 0)
        if index == 0:
            first_name = str(getattr(line, "name", "") or getattr(line, "variant_sku", "") or "").strip()
    if total_qty <= 0:
        total_qty = len(lines)
    noun = "prenda" if total_qty == 1 else "prendas"
    if first_name and len(lines) > 1:
        body = f"{total_qty} {noun}: {first_name} …"
    elif first_name:
        body = f"{total_qty} {noun}: {first_name}"
    else:
        body = f"{total_qty} {noun}"
    if len(body) <= max_len:
        return body
    if max_len <= 1:
        return "…"
    return body[: max_len - 1].rstrip() + "…"


def resolve_cash_session_scope(
    store: CashActivityStore,
    tenant_id: UUID,
    session_id: UUID | None = None,
) -> CashSession | None:
    """Resolve which cash session a feed/list request should use.

    Explicit ``session_id`` wins. Otherwise prefer the open session; if none,
    fall back to the latest closed session from history.
    """
    if session_id is not None:
        for session in store.list_cash_sessions(tenant_id):
            if session.id == session_id:
                return session
        return None
    open_session = store.get_open_cash_session(tenant_id)
    if open_session is not None:
        return open_session
    closed = store.list_cash_sessions(tenant_id, status="closed")
    return closed[0] if closed else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _sort_key(entry: dict[str, Any]) -> tuple[str, str]:
    created = entry.get("created_at") or ""
    return (str(created), str(entry.get("id") or ""))


def build_session_entries(
    movements: list[CashMovement],
    tickets: list[CashSaleTicket],
) -> list[dict[str, Any]]:
    """Build newest-first unified activity entries for one cash session.

    Cash walk-in sales that already have a drawer movement appear once
    (prefer the movement, enrich with ticket number + line summary).
    QR tickets are informational (``affects_cash=false``) and never invent
    fake cash rows.
    """
    tickets_by_id = {ticket.id: ticket for ticket in tickets}
    covered_ticket_ids: set[UUID] = set()
    entries: list[dict[str, Any]] = []

    for movement in movements:
        ticket = tickets_by_id.get(movement.ticket_id) if movement.ticket_id else None
        if ticket is None and movement.ticket_id is None:
            for candidate in tickets:
                if candidate.movement_id == movement.id:
                    ticket = candidate
                    break
        if ticket is not None:
            covered_ticket_ids.add(ticket.id)

        summary = ticket_line_summary(ticket.lines) if ticket is not None else ""
        entries.append(
            {
                "id": str(movement.id),
                "kind": "cash_movement",
                "created_at": _iso(movement.created_at),
                "direction": movement.direction,
                "amount": format_money(movement.amount),
                "currency": movement.currency or "BOB",
                "category": movement.category or "",
                "method": (movement.method or "cash").lower() or "cash",
                "status": movement.status or "recorded",
                "affects_cash": True,
                "reason": movement.reason or "",
                "summary": summary,
                "recorded_by_name": movement.recorded_by_name or "",
                "ticket_id": str(ticket.id) if ticket is not None else (
                    str(movement.ticket_id) if movement.ticket_id else None
                ),
                "ticket_number": ticket.number if ticket is not None else None,
                "session_id": str(movement.session_id) if movement.session_id else None,
                "movement_id": str(movement.id),
            }
        )

    for ticket in tickets:
        if ticket.id in covered_ticket_ids:
            continue
        method = (ticket.method or "").strip().lower()
        if method != "qr":
            # Cash tickets without a movement are rare; skip to avoid inventing rows.
            continue
        status = ticket.status or "pending_qr"
        if status not in {"pending_qr", "recorded", "voided"}:
            continue
        entries.append(
            {
                "id": str(ticket.id),
                "kind": "qr_sale",
                "created_at": _iso(ticket.created_at),
                "direction": None,
                "amount": format_money(ticket.total),
                "currency": ticket.currency or "BOB",
                "category": "venta",
                "method": "qr",
                "status": status,
                "affects_cash": False,
                "reason": f"ticket {ticket.number}",
                "summary": ticket_line_summary(ticket.lines),
                "recorded_by_name": ticket.recorded_by_name or "",
                "ticket_id": str(ticket.id),
                "ticket_number": ticket.number,
                "session_id": str(ticket.session_id) if ticket.session_id else None,
                "movement_id": str(ticket.movement_id) if ticket.movement_id else None,
            }
        )

    entries.sort(key=_sort_key, reverse=True)
    return entries


def _parse_iso_date(raw: str | None) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _entry_date_utc(entry: dict[str, Any]) -> date | None:
    raw = entry.get("created_at")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        created = raw
    else:
        text = str(raw).strip()
        if not text:
            return None
        try:
            created = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return created.astimezone(UTC).date()


def filter_activity_entries(
    entries: list[dict[str, Any]],
    *,
    direction: str | None = None,
    category: str | None = None,
    method: str | None = None,
    status: str | None = None,
    user: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict[str, Any]]:
    """Filter unified activity entries with the same dims as cash movement filters."""
    direction_norm = (direction or "").strip().lower() or None
    category_norm = (category or "").strip().lower() or None
    method_norm = (method or "").strip().lower() or None
    status_norm = (status or "").strip().lower() or None
    user_norm = (user or "").strip().lower() or None
    start = _parse_iso_date(from_date)
    end = _parse_iso_date(to_date)

    filtered: list[dict[str, Any]] = []
    for entry in entries:
        if direction_norm:
            entry_direction = (entry.get("direction") or "").strip().lower()
            if entry_direction != direction_norm:
                continue
        if category_norm and (entry.get("category") or "").strip().lower() != category_norm:
            continue
        if method_norm and (entry.get("method") or "cash").strip().lower() != method_norm:
            continue
        if status_norm and (entry.get("status") or "recorded").strip().lower() != status_norm:
            continue
        if user_norm and user_norm not in (entry.get("recorded_by_name") or "").lower():
            continue
        if start is not None or end is not None:
            day = _entry_date_utc(entry)
            if day is None:
                continue
            if start is not None and day < start:
                continue
            if end is not None and day > end:
                continue
        filtered.append(entry)
    return filtered


def _line_detail(line: CashSaleLine | Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": str(getattr(line, "name", "") or ""),
        "variant_sku": str(getattr(line, "variant_sku", "") or ""),
        "quantity": int(getattr(line, "quantity", 1) or 1),
        "unit_price": format_money(getattr(line, "unit_price", 0)),
        "line_total": format_money(getattr(line, "line_total", 0)),
        "currency": str(getattr(line, "currency", "") or "BOB"),
    }
    talla = getattr(line, "talla", None)
    if talla is None and isinstance(line, dict):
        talla = line.get("talla")
    color = getattr(line, "color", None)
    if color is None and isinstance(line, dict):
        color = line.get("color")
    talla_text = str(talla).strip() if talla is not None else ""
    color_text = str(color).strip() if color is not None else ""
    if talla_text:
        payload["talla"] = talla_text
    if color_text:
        payload["color"] = color_text
    return payload


def activity_detail_payload(
    *,
    kind: str,
    movement: CashMovement | None = None,
    ticket: CashSaleTicket | None = None,
    attachments: list[Any] | None = None,
) -> dict[str, Any]:
    """Assemble a stable activity detail payload from movement and/or ticket."""
    kind_norm = (kind or "").strip().lower()
    if kind_norm not in {"cash_movement", "qr_sale"}:
        raise ValueError("bad_activity_kind")

    attachment_rows = attachments or []
    attachment_items: list[dict[str, Any]] = []
    for item in attachment_rows:
        if isinstance(item, dict):
            attachment_items.append(item)
            continue
        attachment_items.append(
            {
                "id": str(getattr(item, "id", "") or ""),
                "filename": str(getattr(item, "filename", "") or ""),
                "content_type": str(getattr(item, "content_type", "") or ""),
                "size_bytes": int(getattr(item, "size_bytes", 0) or 0),
                "created_at": _iso(getattr(item, "created_at", None)),
            }
        )

    if kind_norm == "qr_sale":
        if ticket is None:
            raise ValueError("activity_not_found")
        return {
            "id": str(ticket.id),
            "kind": "qr_sale",
            "status": ticket.status or "pending_qr",
            "method": "qr",
            "affects_cash": False,
            "direction": None,
            "amount": format_money(ticket.total),
            "currency": ticket.currency or "BOB",
            "category": "venta",
            "reason": f"ticket {ticket.number}",
            "summary": ticket_line_summary(ticket.lines),
            "created_at": _iso(ticket.created_at),
            "recorded_by_name": ticket.recorded_by_name or "",
            "recorded_by_id": str(ticket.recorded_by_id) if ticket.recorded_by_id else None,
            "session_id": str(ticket.session_id) if ticket.session_id else None,
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.number,
            "movement_id": str(ticket.movement_id) if ticket.movement_id else None,
            "lines": [_line_detail(line) for line in ticket.lines],
            "void_reason": None,
            "voided_by_name": None,
            "voided_by_id": None,
            "voided_at": None,
            "attachments_count": 0,
            "attachments": [],
            "attachments_href": None,
        }

    if movement is None:
        raise ValueError("activity_not_found")

    lines = [_line_detail(line) for line in ticket.lines] if ticket is not None else []
    movement_id = str(movement.id)
    return {
        "id": movement_id,
        "kind": "cash_movement",
        "status": movement.status or "recorded",
        "method": (movement.method or "cash").lower() or "cash",
        "affects_cash": True,
        "direction": movement.direction,
        "amount": format_money(movement.amount),
        "currency": movement.currency or "BOB",
        "category": movement.category or "",
        "reason": movement.reason or "",
        "summary": ticket_line_summary(ticket.lines) if ticket is not None else (movement.reason or ""),
        "created_at": _iso(movement.created_at),
        "recorded_by_name": movement.recorded_by_name or "",
        "recorded_by_id": str(movement.recorded_by_id) if movement.recorded_by_id else None,
        "session_id": str(movement.session_id) if movement.session_id else None,
        "ticket_id": (
            str(ticket.id)
            if ticket is not None
            else (str(movement.ticket_id) if movement.ticket_id else None)
        ),
        "ticket_number": ticket.number if ticket is not None else None,
        "movement_id": movement_id,
        "lines": lines,
        "void_reason": movement.void_reason,
        "voided_by_name": movement.voided_by_name,
        "voided_by_id": str(movement.voided_by_id) if movement.voided_by_id else None,
        "voided_at": _iso(movement.voided_at),
        "attachments_count": len(attachment_items),
        "attachments": attachment_items,
        "attachments_href": f"/api/cash/{movement_id}/attachments",
    }
