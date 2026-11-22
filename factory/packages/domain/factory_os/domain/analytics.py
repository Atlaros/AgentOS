"""Analítica facts: one builder for the panel API and metrics.summary.

Period basis
------------
Default ``7d`` is a rolling window of 7×24h ending at ``now``, compared with
the previous 7×24h (equal length). ``today`` and ``month`` use the elapsed
slice of the current America/La_Paz calendar day or month, again compared
with a previous window of that same length. ``range`` is ``[date_from, date_to)``.

Revenue
-------
Counts ``PaymentStatus.CONFIRMED`` only. Pending, expired, and failed do not.
A confirmed payment linked to a voided cash ticket, or to a ticket whose cash
movement is voided, is excluded.

Walk-in cash sales never create a Payment row. A recorded cash ticket whose
movement is not voided counts as revenue and as one sale, matching Caja /
Contabilidad (those inflows post to Ventas). A loose cash-in without a ticket
does not. CxP is omitted: no cheap payable-balance read exists on the store.
Purchases received are included because ``list_purchases`` already exists.

Sales (orders) are the distinct orders touched by a qualifying confirmed
payment in the window, plus walk-in QR payments without an order, plus the
cash tickets above. Reservations without a confirmed payment stay out.

A percent change is ``None`` when the previous window total is 0. That is an
empty previous period, not a fake 0%.

Cash revenue is recorded cash tickets (movement not voided). QR revenue is
confirmed payments. A cash ticket already linked to a counted payment is not
added again, so the two parts sum to the same total as before.

Ticket promedio is revenue/sales. It is empty when that side has no sales —
never a fake 0. Utilidad is revenue minus weighted-average COGS for units
sold in the window. If the tenant has no purchase cost, or any sold SKU lacks
one, the KPI is empty with ``unavailable_reason=missing_costs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from factory_os.domain.analytics_thresholds import AnalyticsThresholds
from factory_os.domain.journal_cogs import weighted_avg_unit_cost
from factory_os.domain.models import Payment, PaymentStatus
from factory_os.domain.reports import inactive_after_for, inactive_customer_rows, overdue_payments
from factory_os.domain.store import CommerceStore
from factory_os.domain.suppliers import list_low_stock, low_stock_public

BUSINESS_TZ = ZoneInfo("America/La_Paz")
PERIOD_IDS = ("today", "7d", "month", "range")

_ALERTS: dict[str, tuple[str, str]] = {
    "low_stock": ("Stock bajo", "/suppliers?tab=reposicion"),
    "payment_overdue": ("Pago vencido", "/reports?tab=seguimiento"),
    "customer_inactive": ("Cliente inactivo", "/reports?tab=seguimiento"),
    "qr_pending_stale": ("QR pendiente", "/orders"),
    "zero_stock_sales": ("Venta con stock en cero", "/suppliers?tab=reposicion"),
}

_KPI_LABELS = {
    "revenue": "Ingresos",
    "sales": "Ventas",
    "avg_ticket": "Ticket promedio",
    "purchases": "Compras recibidas",
    "profit": "Utilidad",
}

_MONTHS_ES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def parse_instant(raw: object | None) -> datetime | None:
    """Parse an ISO instant. Naive values are read as UTC. Blank is None."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def build_analytics_summary(
    store: CommerceStore,
    tenant_id: UUID,
    *,
    period: str = "7d",
    now: datetime | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    """Period KPIs, typed alerts, and the flat keys the Analista template reads."""
    store.require_tenant(tenant_id)
    moment = _as_utc(now) if now is not None else datetime.now(UTC)
    start, end, previous_start, previous_end, period_id = _windows(
        period, moment, date_from, date_to
    )
    thresholds = _thresholds(store, tenant_id)

    payments = list(store.list_payments(tenant_id))
    orders = list(store.list_orders(tenant_id))
    tickets = _list_tickets(store, tenant_id)
    voided_payment_ids, voided_movement_ids = _void_links(tickets, _list_cash(store, tenant_id))

    current = _window_facts(
        payments, tickets, voided_payment_ids, voided_movement_ids, start, end
    )
    previous = _window_facts(
        payments,
        tickets,
        voided_payment_ids,
        voided_movement_ids,
        previous_start,
        previous_end,
    )
    purchase_current, purchase_previous, purchases_available = _purchase_counts(
        store, tenant_id, start, end, previous_start, previous_end
    )

    low_records = list_low_stock(store)
    low_count = len(low_records)
    overdue_count = len(overdue_payments(payments))
    inactive_count = len(
        inactive_customer_rows(
            store.list_customers(tenant_id),
            store.list_conversations(tenant_id),
            moment,
            after=inactive_after_for(store, tenant_id),
        )
    )
    stale_count = _stale_pending_count(
        payments, voided_payment_ids, moment, int(thresholds.qr_pending_hours)
    )
    zero_count = _zero_stock_sales_count(
        store, orders, payments, tickets, voided_payment_ids, voided_movement_ids
    )

    alerts = _alert_rows(
        (
            ("low_stock", low_count),
            ("payment_overdue", overdue_count),
            ("customer_inactive", inactive_count),
            ("qr_pending_stale", stale_count),
            ("zero_stock_sales", zero_count),
        )
    )
    kpis = [
        _kpi("revenue", "money", current.revenue, previous.revenue),
        _kpi("sales", "count", current.sales, previous.sales),
        _avg_ticket_kpi(current.revenue, current.sales, previous.revenue, previous.sales),
    ]
    if purchases_available:
        kpis.append(_kpi("purchases", "count", purchase_current, purchase_previous))
    kpis.append(
        _profit_kpi(
            store,
            tenant_id,
            orders,
            payments,
            tickets,
            voided_payment_ids,
            voided_movement_ids,
            start,
            end,
            previous_start,
            previous_end,
            current.revenue,
            previous.revenue,
        )
    )

    pending_count = sum(
        1
        for payment in payments
        if payment.status is PaymentStatus.PENDING and payment.id not in voided_payment_ids
    )
    reservations = sum(1 for order in orders if order.status == "reserved")
    label_current, label_previous = comparison_labels(start, end, previous_start, previous_end)
    return {
        "period": {
            "id": period_id,
            "basis": "rolling_7x24h" if period_id == "7d" else "equal_elapsed_business_tz",
            "timezone": "America/La_Paz",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "previous_start": previous_start.isoformat(),
            "previous_end": previous_end.isoformat(),
            "previous_end_inclusive": (previous_end - timedelta(microseconds=1)).isoformat(),
            "label_current": label_current,
            "label_previous": label_previous,
        },
        "kpis": kpis,
        "alerts": alerts,
        "alert_type_count": len(alerts),
        "orders": current.sales,
        "reservations": reservations,
        "payments_confirmed": current.payments_confirmed,
        "payments_pending": pending_count,
        "confirmed_amount": _money(current.revenue),
        "revenue_breakdown": {
            "cash": _money(current.cash_revenue),
            "qr": _money(current.qr_revenue),
        },
        "series": {
            "sales_by_day": _sales_by_day(current, previous, start, end, previous_start, previous_end),
            "tender": {
                "cash": _money(current.cash_revenue),
                "qr": _money(current.qr_revenue),
            },
        },
        "low_stock_count": low_count,
        "low_stock": low_stock_public(low_records, limit=10),
    }


def _windows(
    period: str,
    now: datetime,
    date_from: datetime | None,
    date_to: datetime | None,
) -> tuple[datetime, datetime, datetime, datetime, str]:
    period_id = (period or "7d").strip().lower()
    if period_id not in PERIOD_IDS:
        raise ValueError("bad_period")
    if period_id == "7d":
        end = now
        start = now - timedelta(days=7)
    elif period_id == "today":
        local = now.astimezone(BUSINESS_TZ)
        start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        end = now
    elif period_id == "month":
        local = now.astimezone(BUSINESS_TZ)
        start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        end = now
    else:
        if date_from is None or date_to is None:
            raise ValueError("bad_period")
        start = _as_utc(date_from)
        end = _as_utc(date_to)
        if end <= start:
            raise ValueError("bad_period")
    if end < start:
        raise ValueError("bad_period")
    length = end - start
    previous_end = start
    previous_start = start - length
    return start, end, previous_start, previous_end, period_id


def _format_local_date(day: date) -> str:
    return f"{day.day} {_MONTHS_ES[day.month - 1]}"


def _local_date(moment: datetime) -> date:
    return _as_utc(moment).astimezone(BUSINESS_TZ).date()


def inclusive_day_label(moment: datetime) -> str:
    """Calendar day in America/La_Paz for an instant the window includes."""
    return _format_local_date(_local_date(moment))


def exclusive_end_day_label(exclusive_end: datetime) -> str:
    """Date-only label for a half-open end: the La Paz day before that instant.

    ``previous_end`` equals ``start``. Printing that instant as a calendar day
    makes the previous range look like it includes the current start day.
    Facts stay ``start <= t < end``; only the printed day moves back.
    """
    return _format_local_date(_local_date(exclusive_end) - timedelta(days=1))


def comparison_labels(
    start: datetime,
    end: datetime,
    previous_start: datetime,
    previous_end: datetime,
) -> tuple[str, str]:
    """Current range vs previous range, without a shared printed calendar day."""
    current_close = end - timedelta(microseconds=1)
    current = f"{inclusive_day_label(start)} – {inclusive_day_label(current_close)}"
    previous = (
        f"{inclusive_day_label(previous_start)} – {exclusive_end_day_label(previous_end)}"
    )
    return current, previous


@dataclass(frozen=True)
class WindowFacts:
    revenue: Decimal
    sales: int
    payments_confirmed: int
    cash_revenue: Decimal
    qr_revenue: Decimal
    sales_by_day: dict[date, int]


def _window_facts(
    payments: list[Payment],
    tickets: list[Any],
    voided_payment_ids: set[UUID],
    voided_movement_ids: set[UUID],
    start: datetime,
    end: datetime,
) -> WindowFacts:
    qr_revenue = Decimal("0")
    cash_revenue = Decimal("0")
    confirmed_count = 0
    counted_payment_ids: set[UUID] = set()
    order_day: dict[UUID, date] = {}
    loose_days: list[date] = []
    for payment in payments:
        if not _payment_counts(payment, voided_payment_ids):
            continue
        stamp = payment.created_at
        if stamp is None or not _in_window(stamp, start, end):
            continue
        qr_revenue += Decimal(payment.amount)
        confirmed_count += 1
        counted_payment_ids.add(payment.id)
        day = _local_day(stamp)
        if payment.order_id is not None:
            previous_day = order_day.get(payment.order_id)
            if previous_day is None or day < previous_day:
                order_day[payment.order_id] = day
        else:
            loose_days.append(day)
    for ticket in tickets:
        if not _cash_ticket_counts(ticket, voided_movement_ids, voided_payment_ids):
            continue
        if ticket.payment_id is not None and ticket.payment_id in counted_payment_ids:
            continue
        ticket_at = getattr(ticket, "created_at", None)
        if not isinstance(ticket_at, datetime) or not _in_window(ticket_at, start, end):
            continue
        cash_revenue += Decimal(ticket.total)
        loose_days.append(_local_day(ticket_at))
    sales_by_day: dict[date, int] = {}
    for day in order_day.values():
        sales_by_day[day] = sales_by_day.get(day, 0) + 1
    for day in loose_days:
        sales_by_day[day] = sales_by_day.get(day, 0) + 1
    revenue = cash_revenue + qr_revenue
    return WindowFacts(
        revenue=revenue,
        sales=len(order_day) + len(loose_days),
        payments_confirmed=confirmed_count,
        cash_revenue=cash_revenue,
        qr_revenue=qr_revenue,
        sales_by_day=sales_by_day,
    )


def _local_day(stamp: datetime) -> date:
    return _as_utc(stamp).astimezone(BUSINESS_TZ).date()


def _calendar_days(start: datetime, end: datetime) -> list[date]:
    if end <= start:
        return []
    first = _local_day(start)
    last = _local_day(end - timedelta(microseconds=1))
    days: list[date] = []
    cursor = first
    while cursor <= last:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _sales_by_day(
    current: WindowFacts,
    previous: WindowFacts,
    start: datetime,
    end: datetime,
    previous_start: datetime,
    previous_end: datetime,
) -> list[dict[str, Any]]:
    current_days = _calendar_days(start, end)
    previous_days = _calendar_days(previous_start, previous_end)
    rows: list[dict[str, Any]] = []
    width = max(len(current_days), len(previous_days))
    for index in range(width):
        current_day = current_days[index] if index < len(current_days) else None
        previous_day = previous_days[index] if index < len(previous_days) else None
        rows.append(
            {
                "day": current_day.isoformat() if current_day is not None else "",
                "current": current.sales_by_day.get(current_day, 0) if current_day is not None else 0,
                "previous": previous.sales_by_day.get(previous_day, 0) if previous_day is not None else 0,
            }
        )
    return rows


def _avg_ticket_kpi(
    current_revenue: Decimal,
    current_sales: int,
    previous_revenue: Decimal,
    previous_sales: int,
) -> dict[str, Any]:
    current_empty = current_sales <= 0
    previous_empty = previous_sales <= 0
    current_avg = None if current_empty else current_revenue / Decimal(current_sales)
    previous_avg = None if previous_empty else previous_revenue / Decimal(previous_sales)
    pct = None
    if previous_avg is not None:
        current_for_pct = current_avg if current_avg is not None else Decimal("0")
        pct = _pct(current_for_pct, previous_avg)
    return {
        "id": "avg_ticket",
        "label": _KPI_LABELS["avg_ticket"],
        "kind": "money",
        "current": None if current_avg is None else _money(current_avg),
        "previous": None if previous_avg is None else _money(previous_avg),
        "pct_change": pct,
        "previous_empty": previous_empty,
        "current_empty": current_empty,
    }


def _unavailable_profit() -> dict[str, Any]:
    return {
        "id": "profit",
        "label": _KPI_LABELS["profit"],
        "kind": "money",
        "current": None,
        "previous": None,
        "pct_change": None,
        "previous_empty": True,
        "current_empty": True,
        "unavailable_reason": "missing_costs",
    }


def _profit_kpi(
    store: CommerceStore,
    tenant_id: UUID,
    orders: list[Any],
    payments: list[Payment],
    tickets: list[Any],
    voided_payment_ids: set[UUID],
    voided_movement_ids: set[UUID],
    start: datetime,
    end: datetime,
    previous_start: datetime,
    previous_end: datetime,
    current_revenue: Decimal,
    previous_revenue: Decimal,
) -> dict[str, Any]:
    if not _tenant_has_unit_cost(store, tenant_id):
        return _unavailable_profit()
    current = _period_profit(
        store,
        tenant_id,
        orders,
        payments,
        tickets,
        voided_payment_ids,
        voided_movement_ids,
        start,
        end,
        current_revenue,
    )
    previous = _period_profit(
        store,
        tenant_id,
        orders,
        payments,
        tickets,
        voided_payment_ids,
        voided_movement_ids,
        previous_start,
        previous_end,
        previous_revenue,
    )
    if current is None:
        return _unavailable_profit()
    if previous is None:
        row = _kpi("profit", "money", current, Decimal("0"))
        row["previous"] = None
        row["previous_empty"] = True
        row["pct_change"] = None
        return row
    return _kpi("profit", "money", current, previous)


def _tenant_has_unit_cost(store: CommerceStore, tenant_id: UUID) -> bool:
    list_fn = getattr(store, "list_purchases", None)
    if not callable(list_fn):
        return False
    for receipt in list_fn(tenant_id):
        quantity = int(getattr(receipt, "quantity", 0) or 0)
        cost = getattr(receipt, "unit_cost", None)
        if quantity >= 1 and cost is not None and Decimal(str(cost)) > 0:
            return True
    return False


def _period_profit(
    store: CommerceStore,
    tenant_id: UUID,
    orders: list[Any],
    payments: list[Payment],
    tickets: list[Any],
    voided_payment_ids: set[UUID],
    voided_movement_ids: set[UUID],
    start: datetime,
    end: datetime,
    revenue: Decimal,
) -> Decimal | None:
    quantities, complete = _sold_quantities(
        orders,
        payments,
        tickets,
        voided_payment_ids,
        voided_movement_ids,
        start,
        end,
    )
    if not complete:
        return None
    cogs = Decimal("0")
    for sku, units in quantities.items():
        unit = weighted_avg_unit_cost(store, tenant_id, sku)
        if unit is None:
            return None
        cogs += (unit * Decimal(units)).quantize(Decimal("0.01"))
    return (revenue - cogs).quantize(Decimal("0.01"))


def _sold_quantities(
    orders: list[Any],
    payments: list[Payment],
    tickets: list[Any],
    voided_payment_ids: set[UUID],
    voided_movement_ids: set[UUID],
    start: datetime,
    end: datetime,
) -> tuple[dict[str, int], bool]:
    """Units sold in the window. The bool is False when COGS would be a guess."""
    orders_by_id = {order.id: order for order in orders}
    tickets_by_payment: dict[UUID, list[Any]] = {}
    for ticket in tickets:
        payment_id = getattr(ticket, "payment_id", None)
        if payment_id is not None:
            tickets_by_payment.setdefault(payment_id, []).append(ticket)

    quantities: dict[str, int] = {}
    complete = True
    seen_orders: set[UUID] = set()
    counted_payment_ids: set[UUID] = set()
    for payment in payments:
        if not _payment_counts(payment, voided_payment_ids):
            continue
        if not _in_window(payment.created_at, start, end):
            continue
        counted_payment_ids.add(payment.id)
        if payment.order_id is not None:
            if payment.order_id in seen_orders:
                continue
            seen_orders.add(payment.order_id)
            order = orders_by_id.get(payment.order_id)
            if order is None or getattr(order, "status", "") == "cancelled":
                complete = False
                continue
            if not _absorb_lines(quantities, getattr(order, "items", []) or []):
                complete = False
            continue
        linked_lines: list[Any] = []
        for ticket in tickets_by_payment.get(payment.id, []):
            if (getattr(ticket, "status", "") or "") != "recorded":
                continue
            linked_lines.extend(getattr(ticket, "lines", []) or [])
        if not _absorb_lines(quantities, linked_lines):
            complete = False

    for ticket in tickets:
        if not _cash_ticket_counts(ticket, voided_movement_ids, voided_payment_ids):
            continue
        if ticket.payment_id is not None and ticket.payment_id in counted_payment_ids:
            continue
        if not _in_window(ticket.created_at, start, end):
            continue
        if not _absorb_lines(quantities, getattr(ticket, "lines", []) or []):
            complete = False
    return quantities, complete


def _absorb_lines(quantities: dict[str, int], lines: list[Any]) -> bool:
    if not lines:
        return False
    accepted = 0
    valid = True
    for line in lines:
        sku = (getattr(line, "variant_sku", "") or "").strip()
        units = int(getattr(line, "quantity", 0) or 0)
        if not sku or units < 1:
            valid = False
            continue
        quantities[sku] = quantities.get(sku, 0) + units
        accepted += 1
    return valid and accepted > 0


def _payment_counts(payment: Payment, voided_payment_ids: set[UUID]) -> bool:
    return payment.status is PaymentStatus.CONFIRMED and payment.id not in voided_payment_ids


def _cash_ticket_counts(
    ticket: Any, voided_movement_ids: set[UUID], voided_payment_ids: set[UUID]
) -> bool:
    if (getattr(ticket, "method", "") or "").lower() != "cash":
        return False
    if (getattr(ticket, "status", "") or "") != "recorded":
        return False
    movement_id = getattr(ticket, "movement_id", None)
    if movement_id is not None and movement_id in voided_movement_ids:
        return False
    payment_id = getattr(ticket, "payment_id", None)
    if payment_id is not None and payment_id in voided_payment_ids:
        return False
    return True


def _purchase_counts(
    store: CommerceStore,
    tenant_id: UUID,
    start: datetime,
    end: datetime,
    previous_start: datetime,
    previous_end: datetime,
) -> tuple[int, int, bool]:
    list_fn = getattr(store, "list_purchases", None)
    if not callable(list_fn):
        return 0, 0, False
    current = 0
    previous = 0
    for receipt in list_fn(tenant_id):
        stamp = getattr(receipt, "received_at", None) or getattr(receipt, "created_at", None)
        if _in_window(stamp, start, end):
            current += 1
        elif _in_window(stamp, previous_start, previous_end):
            previous += 1
    return current, previous, True


def _void_links(tickets: list[Any], movements: list[Any]) -> tuple[set[UUID], set[UUID]]:
    voided_movement_ids = {
        movement.id for movement in movements if (getattr(movement, "status", "") or "") == "voided"
    }
    voided_payment_ids: set[UUID] = set()
    for ticket in tickets:
        movement_id = getattr(ticket, "movement_id", None)
        movement_void = movement_id is not None and movement_id in voided_movement_ids
        if (getattr(ticket, "status", "") or "") == "voided" or movement_void:
            payment_id = getattr(ticket, "payment_id", None)
            if payment_id is not None:
                voided_payment_ids.add(payment_id)
            if movement_id is not None:
                voided_movement_ids.add(movement_id)
    return voided_payment_ids, voided_movement_ids


def _stale_pending_count(
    payments: list[Payment],
    voided_payment_ids: set[UUID],
    now: datetime,
    qr_pending_hours: int,
) -> int:
    cutoff = now - timedelta(hours=max(1, qr_pending_hours))
    count = 0
    for payment in payments:
        if payment.status is not PaymentStatus.PENDING or payment.id in voided_payment_ids:
            continue
        stamp = _as_utc(payment.created_at) if payment.created_at is not None else None
        if stamp is not None and stamp <= cutoff:
            count += 1
    return count


def _zero_stock_sales_count(
    store: CommerceStore,
    orders: list[Any],
    payments: list[Payment],
    tickets: list[Any],
    voided_payment_ids: set[UUID],
    voided_movement_ids: set[UUID],
) -> int:
    qualifying = {
        payment.id: payment
        for payment in payments
        if _payment_counts(payment, voided_payment_ids)
    }
    paid_orders = {payment.order_id for payment in qualifying.values() if payment.order_id}
    sold: set[str] = set()
    for order in orders:
        if order.id not in paid_orders or order.status == "cancelled":
            continue
        for item in order.items:
            if item.variant_sku:
                sold.add(item.variant_sku)
    for ticket in tickets:
        if (getattr(ticket, "status", "") or "") != "recorded":
            continue
        movement_id = getattr(ticket, "movement_id", None)
        if movement_id is not None and movement_id in voided_movement_ids:
            continue
        payment_id = getattr(ticket, "payment_id", None)
        method = (getattr(ticket, "method", "") or "").lower()
        if method != "cash" and (payment_id is None or payment_id not in qualifying):
            continue
        for line in getattr(ticket, "lines", []) or []:
            sku = getattr(line, "variant_sku", "") or ""
            if sku:
                sold.add(sku)
    count = 0
    for record in store.iter_variants():
        if record.variant_sku not in sold:
            continue
        if (record.attributes or {}).get("disabled"):
            continue
        if int(record.stock) <= 0:
            count += 1
    return count


def _alert_rows(pairs: tuple[tuple[str, int], ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for alert_type, count in pairs:
        if count <= 0:
            continue
        label, href = _ALERTS[alert_type]
        rows.append({"type": alert_type, "count": int(count), "href": href, "label": label})
    return rows


def _kpi(kpi_id: str, kind: str, current: Decimal | int, previous: Decimal | int) -> dict[str, Any]:
    current_value = Decimal(current)
    previous_value = Decimal(previous)
    if kind == "money":
        shown_current: str | int = _money(current_value)
        shown_previous: str | int = _money(previous_value)
    else:
        shown_current = int(current_value)
        shown_previous = int(previous_value)
    return {
        "id": kpi_id,
        "label": _KPI_LABELS[kpi_id],
        "kind": kind,
        "current": shown_current,
        "previous": shown_previous,
        "pct_change": _pct(current_value, previous_value),
        "previous_empty": previous_value == 0,
        "current_empty": current_value == 0,
    }


def _pct(current: Decimal, previous: Decimal) -> float | None:
    if previous == 0:
        return None
    ratio = ((current - previous) / previous) * Decimal("100")
    return float(ratio.quantize(Decimal("0.1")))


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _thresholds(store: CommerceStore, tenant_id: UUID) -> AnalyticsThresholds:
    getter = getattr(store, "get_analytics_thresholds", None)
    if not callable(getter):
        return AnalyticsThresholds()
    loaded = getter(tenant_id)
    if isinstance(loaded, AnalyticsThresholds):
        return loaded
    return AnalyticsThresholds()


def _list_tickets(store: CommerceStore, tenant_id: UUID) -> list[Any]:
    list_fn = getattr(store, "list_cash_sale_tickets", None)
    if not callable(list_fn):
        return []
    return list(list_fn(tenant_id))


def _list_cash(store: CommerceStore, tenant_id: UUID) -> list[Any]:
    list_fn = getattr(store, "list_cash", None)
    if not callable(list_fn):
        return []
    return list(list_fn(tenant_id))


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _in_window(stamp: datetime | None, start: datetime, end: datetime) -> bool:
    if stamp is None:
        return False
    moment = _as_utc(stamp)
    return start <= moment < end
