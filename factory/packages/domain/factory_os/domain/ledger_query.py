"""Ledger period filters and hydrated read models for Contabilidad (ADR-010)."""

from __future__ import annotations

import calendar
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from factory_os.domain.ledger import entry_is_recorded
from factory_os.domain.models import LedgerEntry
from factory_os.domain.store import CommerceStore

_TK_RE = re.compile(r"\bTK-[A-Z0-9]+\b", re.IGNORECASE)
_PERIOD_PRESETS = frozenset({"today", "week", "month"})


def resolve_ledger_period(
    preset: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    *,
    now: datetime | None = None,
) -> tuple[date, date, str | None]:
    """Return inclusive UTC calendar bounds and the effective preset label.

    Explicit ISO ``from``/``to`` override the preset. Default preset is ``month``.
    """
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)
    else:
        clock = clock.astimezone(UTC)
    today = clock.date()

    raw_from = (date_from or "").strip()
    raw_to = (date_to or "").strip()
    if raw_from or raw_to:
        start = _parse_iso_date(raw_from) or today
        end = _parse_iso_date(raw_to) or today
        if end < start:
            start, end = end, start
        return start, end, None

    chosen = (preset or "month").strip().lower() or "month"
    if chosen not in _PERIOD_PRESETS:
        chosen = "month"

    if chosen == "today":
        return today, today, chosen
    if chosen == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start, end, chosen

    start = today.replace(day=1)
    last_day = calendar.monthrange(today.year, today.month)[1]
    end = today.replace(day=last_day)
    return start, end, "month"


def filter_ledger_entries(
    entries: list[LedgerEntry] | list[dict[str, Any]],
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    source: str | None = None,
    status: str | None = None,
    category: str | None = None,
    method: str | None = None,
) -> list[Any]:
    """Filter ledger rows by UTC day and optional source/status/category/method."""
    source_norm = (source or "").strip().lower() or None
    status_norm = (status or "").strip().lower() or None
    category_norm = (category or "").strip().lower() or None
    method_norm = (method or "").strip().lower() or None

    filtered: list[Any] = []
    for item in entries:
        if isinstance(item, dict):
            item_source = str(item.get("source") or "")
            item_status = str(item.get("status") or "recorded")
            item_category = item.get("category")
            item_method = item.get("method")
            day = _created_day_utc(item.get("created_at"))
        else:
            item_source = item.source
            item_status = item.status or "recorded"
            item_category = None
            item_method = None
            day = _created_day_utc(item.created_at)

        if source_norm and item_source.strip().lower() != source_norm:
            continue
        if status_norm and item_status.strip().lower() != status_norm:
            continue
        if category_norm is not None:
            if item_category is None:
                continue
            if str(item_category).strip().lower() != category_norm:
                continue
        if method_norm is not None:
            if item_method is None:
                continue
            if str(item_method).strip().lower() != method_norm:
                continue
        if date_from is not None or date_to is not None:
            if day is None:
                continue
            if date_from is not None and day < date_from:
                continue
            if date_to is not None and day > date_to:
                continue
        filtered.append(item)
    return filtered


def hydrate_ledger_entry(store: CommerceStore, tenant_id: UUID, entry: LedgerEntry) -> dict[str, Any]:
    """Enrich a ledger fact with origin category/method/reference for the panel."""
    store.require_tenant(tenant_id)
    payload: dict[str, Any] = {
        "id": str(entry.id),
        "source": entry.source,
        "source_id": str(entry.source_id),
        "direction": entry.direction,
        "amount": str(entry.amount),
        "currency": entry.currency,
        "status": entry.status or "recorded",
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "category": "",
        "method": "",
        "reference_label": "",
        "reference_href": None,
    }

    if entry.source == "cash":
        _hydrate_cash(store, tenant_id, entry, payload)
    elif entry.source == "payment":
        _hydrate_payment(store, tenant_id, entry, payload)
    elif entry.source == "purchase":
        _hydrate_purchase(store, tenant_id, entry, payload)
    return payload


def period_totals_entries(
    entries: list[LedgerEntry],
    *,
    date_from: date,
    date_to: date,
) -> list[LedgerEntry]:
    """Entries in the period used for recorded-only totals (status filter ignored)."""
    return [
        entry
        for entry in filter_ledger_entries(entries, date_from=date_from, date_to=date_to)
        if entry_is_recorded(entry)
    ]


def _hydrate_cash(
    store: CommerceStore,
    tenant_id: UUID,
    entry: LedgerEntry,
    payload: dict[str, Any],
) -> None:
    movement = store.get_cash_movement(tenant_id, entry.source_id)
    if movement is None:
        payload["reference_label"] = str(entry.source_id)[:8]
        payload["reference_href"] = "/cash?tab=movements"
        return
    payload["category"] = (movement.category or "").strip()
    payload["method"] = (movement.method or "cash").strip() or "cash"
    label = (movement.reason or "").strip()
    ticket_label = _ticket_label(store, tenant_id, movement.ticket_id, movement.reason)
    if ticket_label:
        label = ticket_label
    payload["reference_label"] = label or str(entry.source_id)[:8]
    payload["reference_href"] = "/cash?tab=movements"


def _hydrate_payment(
    store: CommerceStore,
    tenant_id: UUID,
    entry: LedgerEntry,
    payload: dict[str, Any],
) -> None:
    payment = store.get_payment(tenant_id, entry.source_id)
    if payment is None:
        payload["method"] = "qr"
        payload["reference_label"] = str(entry.source_id)[:8]
        return
    provider = (payment.provider or "").strip().lower()
    payload["method"] = "qr" if provider in {"", "fake", "baneco", "qr"} else provider
    payload["category"] = ""
    ref = (payment.provider_ref or "").strip() or str(payment.id)[:8]
    payload["reference_label"] = ref
    payload["reference_href"] = "/orders" if payment.order_id else None


def _hydrate_purchase(
    store: CommerceStore,
    tenant_id: UUID,
    entry: LedgerEntry,
    payload: dict[str, Any],
) -> None:
    payload["category"] = "compra"
    payload["method"] = "cash"
    receipt = _find_purchase(store, tenant_id, entry.source_id)
    if receipt is not None:
        payload["reference_label"] = receipt.variant_sku
    else:
        payload["reference_label"] = str(entry.source_id)[:8]
    payload["reference_href"] = None


def _find_purchase(store: CommerceStore, tenant_id: UUID, purchase_id: UUID) -> Any | None:
    purchases = getattr(store, "purchases", None)
    if isinstance(purchases, list):
        for receipt in purchases:
            if getattr(receipt, "tenant_id", None) == tenant_id and getattr(receipt, "id", None) == purchase_id:
                return receipt
    list_fn = getattr(store, "list_purchases", None)
    if callable(list_fn):
        for receipt in list_fn(tenant_id):
            if getattr(receipt, "id", None) == purchase_id:
                return receipt
    return None


def _ticket_label(
    store: CommerceStore,
    tenant_id: UUID,
    ticket_id: UUID | None,
    reason: str | None,
) -> str:
    if ticket_id is not None:
        ticket = store.get_cash_sale_ticket(tenant_id, ticket_id)
        if ticket is not None and (ticket.number or "").strip():
            return ticket.number.strip()
    match = _TK_RE.search(reason or "")
    if match:
        return match.group(0).upper()
    return ""


def _parse_iso_date(raw: str | None) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _created_day_utc(raw: datetime | str | None) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            created = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return _parse_iso_date(text)
    else:
        created = raw
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return created.astimezone(UTC).date()
