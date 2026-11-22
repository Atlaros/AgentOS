"""Owner reports, alerts, and reminder notices.

Notices are fixed operational text. They do not quote a price, recommend a
product, or change a payment.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO, StringIO
from typing import Any
from urllib.parse import quote
from uuid import UUID

from factory_os.contracts.employees import EmployeeRole, Identity
from factory_os.domain.models import Payment, PaymentStatus
from factory_os.domain.store import CommerceStore

INACTIVE_AFTER = timedelta(days=30)
FOLLOW_UP_AFTER = timedelta(days=1)
REPURCHASE_AFTER = timedelta(days=30)


def inactive_after_for(store: CommerceStore, tenant_id: UUID) -> timedelta:
    """Inactive-customer clock. Defaults stay 30 days when the tenant has not edited them."""
    getter = getattr(store, "get_analytics_thresholds", None)
    if not callable(getter):
        return INACTIVE_AFTER
    try:
        thresholds = getter(tenant_id)
        days = int(getattr(thresholds, "inactive_days"))
    except (TypeError, ValueError, AttributeError):
        return INACTIVE_AFTER
    if days < 1:
        return INACTIVE_AFTER
    return timedelta(days=days)


NOTICE_BODIES: dict[str, str] = {
    "follow_up": "Quedó pendiente tu consulta. Cuando quieras, seguimos por este chat.",
    "repurchase": "Pasó un tiempo desde tu última compra. Si necesitás algo del local, escribinos por acá.",
    "collections": (
        "El QR de tu pedido venció y el pago no está confirmado. "
        "Si todavía lo querés, pedí un QR nuevo por este chat."
    ),
}

SEND_ROLE: dict[str, EmployeeRole] = {
    "follow_up": EmployeeRole.POSTVENTA,
    "repurchase": EmployeeRole.POSTVENTA,
    "collections": EmployeeRole.COBROS,
}


@dataclass(frozen=True)
class PlannedNotice:
    customer_id: UUID
    kind: str
    body: str


def overdue_payments(payments: list[Payment]) -> list[Payment]:
    return [payment for payment in payments if payment.status is PaymentStatus.EXPIRED]


def inactive_customer_rows(
    customers: list[Any],
    conversations: list[Any],
    now: datetime,
    *,
    after: timedelta = INACTIVE_AFTER,
) -> list[tuple[Any, datetime]]:
    latest: dict[UUID, datetime] = {}
    for conversation in conversations:
        seen = conversation.last_message_at
        if seen is None:
            continue
        current = latest.get(conversation.customer_id)
        if current is None or seen > current:
            latest[conversation.customer_id] = seen
    cutoff = now - after
    rows: list[tuple[Any, datetime]] = []
    for customer in customers:
        seen = latest.get(customer.id)
        if seen is not None and seen <= cutoff:
            rows.append((customer, seen))
    return rows


def plan_notices(store: CommerceStore, tenant_id: UUID, now: datetime) -> list[PlannedNotice]:
    store.require_tenant(tenant_id)
    customers = store.list_customers(tenant_id)
    orders = [
        order
        for order in store.list_orders(tenant_id)
        if order.status != "cancelled" and getattr(order, "origin", "agent") != "counter"
    ]
    payments = store.list_payments(tenant_id)
    orders_by_customer: dict[UUID, list[Any]] = {}
    for order in orders:
        orders_by_customer.setdefault(order.customer_id, []).append(order)
    confirmed_customers = {
        payment.customer_id
        for payment in payments
        if payment.status is PaymentStatus.CONFIRMED and payment.customer_id is not None
    }
    for payment in payments:
        if payment.status is not PaymentStatus.CONFIRMED or payment.order_id is None:
            continue
        order = store.get_order(tenant_id, payment.order_id)
        if order is not None:
            confirmed_customers.add(order.customer_id)

    notices: list[PlannedNotice] = []
    follow_cutoff = now - FOLLOW_UP_AFTER
    for customer, seen in inactive_customer_rows(
        customers,
        store.list_conversations(tenant_id),
        now,
        after=FOLLOW_UP_AFTER,
    ):
        if seen > follow_cutoff:
            continue
        if orders_by_customer.get(customer.id):
            continue
        notices.append(
            PlannedNotice(customer.id, "follow_up", NOTICE_BODIES["follow_up"])
        )

    repurchase_cutoff = now - REPURCHASE_AFTER
    for customer in customers:
        owned = orders_by_customer.get(customer.id, [])
        bought = [
            order
            for order in owned
            if order.status == "delivered" or customer.id in confirmed_customers
        ]
        if not bought:
            continue
        latest = max((order.created_at for order in bought if order.created_at is not None), default=None)
        if latest is None or latest > repurchase_cutoff:
            continue
        notices.append(
            PlannedNotice(customer.id, "repurchase", NOTICE_BODIES["repurchase"])
        )

    for payment in overdue_payments(payments):
        customer_id = payment.customer_id
        if customer_id is None and payment.order_id is not None:
            order = store.get_order(tenant_id, payment.order_id)
            customer_id = order.customer_id if order is not None else None
        if customer_id is None:
            continue
        notices.append(
            PlannedNotice(customer_id, "collections", NOTICE_BODIES["collections"])
        )
    unique: list[PlannedNotice] = []
    seen: set[tuple[UUID, str]] = set()
    for notice in notices:
        key = (notice.customer_id, notice.kind)
        if key in seen:
            continue
        seen.add(key)
        unique.append(notice)
    return unique


def run_reminders(
    store: CommerceStore,
    identity: Identity,
    channel: Any,
    tools: Any,
    *,
    now: datetime,
    send: bool,
) -> dict[str, list[dict[str, str]]]:
    """Store due notices. Send only when this employee is allowed to, via the channel."""
    tenant_id = identity.tenant_id
    store.require_tenant(tenant_id)
    existing = {
        (item.customer_id, item.kind): item for item in store.list_reminders(tenant_id)
    }
    created: list[dict[str, str]] = []
    sent: list[dict[str, str]] = []
    for notice in plan_notices(store, tenant_id, now):
        reminder = existing.get((notice.customer_id, notice.kind))
        if reminder is None:
            reminder = store.add_reminder(
                tenant_id, notice.customer_id, notice.kind, notice.body
            )
            existing[(notice.customer_id, notice.kind)] = reminder
            created.append(_public(reminder))
        if reminder.sent_at is not None or not send:
            continue
        if not _deliver(store, identity, channel, tools, reminder):
            continue
        sent.append(_public(reminder))
    return {"created": created, "sent": sent}


REPORT_PERIODS = ("today", "7d", "month", "range")

OPERATIVE_REPORT_CARDS: tuple[dict[str, str], ...] = (
    {
        "id": "orders",
        "label": "Ventas",
        "description": "Pedidos del período con número, estado y total.",
    },
    {
        "id": "payments",
        "label": "Cobros",
        "description": "Cobros del período con referencia, estado y monto.",
    },
    {
        "id": "stock",
        "label": "Inventario",
        "description": "Foto actual de cada variante y su stock. El período no cambia esta lista.",
    },
)

# Contabilidad Descargas cards (ADR-014 frontera / ADR-011 Fase C). Engines live under /api/ledger|journal.
ACCOUNTING_REPORT_CARDS: tuple[dict[str, str], ...] = (
    {
        "id": "ledger_hechos",
        "label": "Hechos",
        "description": "Movimientos del libro operativo del período (pagos, caja y compras).",
    },
    {
        "id": "journal",
        "label": "Diario",
        "description": "Asientos de partida doble del período, con debe y haber.",
    },
    {
        "id": "mayor",
        "label": "Mayor",
        "description": "Movimientos por cuenta con saldo corrido del período.",
    },
    {
        "id": "comprobacion",
        "label": "Comprobación",
        "description": "Totales de debe y haber por cuenta para verificar que cuadra.",
    },
    {
        "id": "resultado",
        "label": "Resultado",
        "description": "Ingresos, costos y gastos del período (resultado gerencial).",
    },
    {
        "id": "balance",
        "label": "Balance",
        "description": "Activos, pasivos y patrimonio al cierre del período.",
    },
)

REPORT_CARDS: tuple[dict[str, str], ...] = OPERATIVE_REPORT_CARDS + ACCOUNTING_REPORT_CARDS

ACCOUNTING_REPORT_IDS = frozenset(card["id"] for card in ACCOUNTING_REPORT_CARDS)

# Path + preferred format query value per Descargas format key (reuse Contabilidad exports).
_ACCOUNTING_DOWNLOAD_SPEC: dict[str, tuple[str, dict[str, str]]] = {
    "ledger_hechos": ("/api/ledger/export", {"csv": "csv", "xlsx": "xlsx"}),
    "journal": ("/api/journal/export", {"csv": "csv", "xlsx": "xlsx"}),
    "mayor": ("/api/journal/ledger", {"csv": "xlsx", "xlsx": "xlsx"}),
    "comprobacion": ("/api/journal/trial-balance", {"csv": "csv", "xlsx": "xlsx"}),
    "resultado": ("/api/journal/income", {"csv": "xlsx", "xlsx": "xlsx"}),
    "balance": ("/api/journal/balance-sheet", {"csv": "xlsx", "xlsx": "xlsx"}),
}


def parse_report_instant(raw: str | None) -> datetime | None:
    """ISO instant for a download window. Blank is absent. Bad text is ``bad_period``."""
    from factory_os.domain.analytics import parse_instant

    try:
        return parse_instant(raw)
    except ValueError as exc:
        raise ValueError("bad_period") from exc


def report_window(
    period: str | None,
    *,
    now: datetime,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[datetime, datetime] | None:
    """``[start, end)`` in UTC, or ``None`` when the caller wants the full dump.

    ``today`` and ``month`` use the elapsed America/La_Paz slice, same as Analítica.
    ``7d`` is the last 7×24h. ``range`` is half-open. No period and no dates keeps
    every row so older links stay a full dump.
    """
    from factory_os.domain.analytics import BUSINESS_TZ

    period_id = (period or "").strip().lower()
    if not period_id and date_from is None and date_to is None:
        return None
    if not period_id:
        period_id = "range"
    if period_id not in REPORT_PERIODS:
        raise ValueError("bad_period")
    moment = _as_utc(now)
    if period_id == "7d":
        end = moment
        start = moment - timedelta(days=7)
    elif period_id == "today":
        local = moment.astimezone(BUSINESS_TZ)
        start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        end = moment
    elif period_id == "month":
        local = moment.astimezone(BUSINESS_TZ)
        start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        end = moment
    else:
        if date_from is None or date_to is None:
            raise ValueError("bad_period")
        start = _as_utc(date_from)
        end = _as_utc(date_to)
        if end <= start:
            raise ValueError("bad_period")
    if end < start:
        raise ValueError("bad_period")
    return start, end


def orders_csv(
    store: CommerceStore,
    tenant_id: UUID,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> str:
    from factory_os.domain.cart_quote import charge_total

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["public_number", "status", "customer_id", "total", "currency"])
    for order in _dated_rows(store.list_orders(tenant_id), start, end, lambda row: row.created_at):
        if getattr(order, "origin", "agent") == "counter":
            continue
        currency = order.items[0].currency if order.items else "BOB"
        writer.writerow(
            [
                order.public_number or "",
                order.status,
                str(order.customer_id),
                str(charge_total(order.items, order.discount_amount)),
                currency,
            ]
        )
    return buffer.getvalue()


def payments_csv(
    store: CommerceStore,
    tenant_id: UUID,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["provider_ref", "status", "amount", "currency", "order_id"])
    for payment in _dated_rows(
        store.list_payments(tenant_id), start, end, lambda row: row.created_at
    ):
        writer.writerow(
            [
                payment.provider_ref,
                payment.status.value,
                str(payment.amount),
                payment.currency,
                str(payment.order_id or ""),
            ]
        )
    return buffer.getvalue()


def stock_csv(
    store: CommerceStore,
    tenant_id: UUID,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> str:
    """Current variant snapshot. Period bounds are ignored: stock is not a dated log."""
    del start, end
    store.require_tenant(tenant_id)
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["variant_sku", "name", "stock"])
    for record in store.iter_variants():
        writer.writerow([record.variant_sku, record.name, record.stock])
    return buffer.getvalue()


def excel_available() -> bool:
    """True when a workbook library is installed. CSV and ZIP do not need it."""
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        return False
    return True


def report_catalog(
    store: CommerceStore,
    tenant_id: UUID,
    *,
    period: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Cards for Descargas. Counts follow the same window as the CSV export."""
    store.require_tenant(tenant_id)
    moment = now if now is not None else datetime.now(UTC)
    window = report_window(
        period,
        now=moment,
        date_from=parse_report_instant(date_from),
        date_to=parse_report_instant(date_to),
    )
    start, end = window if window is not None else (None, None)
    accounting_period, accounting_from, accounting_to = contabilidad_period_params(
        period,
        date_from=date_from,
        date_to=date_to,
        now=moment,
    )
    cards = []
    for spec in REPORT_CARDS:
        report_id = spec["id"]
        if report_id in ACCOUNTING_REPORT_IDS:
            row_count = _accounting_row_count(
                store,
                tenant_id,
                report_id,
                period=accounting_period,
                date_from=accounting_from,
                date_to=accounting_to,
                now=moment,
            )
            downloads = _accounting_download_paths(
                report_id,
                period=accounting_period,
                date_from=accounting_from,
                date_to=accounting_to,
            )
        else:
            row_count = _report_row_count(store, tenant_id, report_id, start, end)
            downloads = _download_paths(
                report_id, period=period, date_from=date_from, date_to=date_to
            )
        cards.append(
            {
                "id": report_id,
                "label": spec["label"],
                "description": spec["description"],
                "row_count": row_count,
                "downloads": downloads,
            }
        )
    return {"reports": cards, "excel_available": excel_available()}


def contabilidad_period_params(
    period: str | None,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    now: datetime | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Map Descargas period to Contabilidad ``period`` or inclusive ``from``/``to`` days.

    ``today`` / ``month`` keep Contabilidad presets. ``7d`` and ``range`` become
    explicit calendar bounds so links match the Descargas toolbar window.
    """
    moment = now if now is not None else datetime.now(UTC)
    period_id = (period or "").strip().lower()
    if period_id == "range" or (
        period_id not in {"", "today", "month", "7d"} and date_from and date_to
    ):
        start = parse_report_instant(date_from)
        end = parse_report_instant(date_to)
        if start is None or end is None:
            raise ValueError("bad_period")
        start_u = _as_utc(start)
        end_u = _as_utc(end)
        if end_u <= start_u:
            raise ValueError("bad_period")
        last = end_u - timedelta(microseconds=1)
        return None, start_u.date().isoformat(), last.date().isoformat()
    if period_id == "7d":
        window = report_window("7d", now=moment)
        if window is None:
            raise ValueError("bad_period")
        start_u, end_u = window
        last = end_u - timedelta(microseconds=1) if end_u > start_u else end_u
        return None, start_u.date().isoformat(), last.date().isoformat()
    if period_id == "today":
        return "today", None, None
    # Empty period still defaults Contabilidad cards to the open month (same as /ledger).
    return "month", None, None


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _in_window(stamp: datetime | None, start: datetime, end: datetime) -> bool:
    if stamp is None:
        return False
    return start <= _as_utc(stamp) < end


def _dated_rows(rows: list[Any], start: datetime | None, end: datetime | None, stamp_of: Any) -> list[Any]:
    if start is None or end is None:
        return list(rows)
    return [row for row in rows if _in_window(stamp_of(row), start, end)]


def _report_row_count(
    store: CommerceStore,
    tenant_id: UUID,
    report_id: str,
    start: datetime | None,
    end: datetime | None,
) -> int:
    if report_id == "orders":
        rows = [
            order
            for order in store.list_orders(tenant_id)
            if getattr(order, "origin", "agent") != "counter"
        ]
        return len(_dated_rows(rows, start, end, lambda row: row.created_at))
    if report_id == "payments":
        return len(_dated_rows(store.list_payments(tenant_id), start, end, lambda row: row.created_at))
    if report_id == "stock":
        store.require_tenant(tenant_id)
        return sum(1 for _record in store.iter_variants())
    raise ValueError("unknown_report")


def _accounting_row_count(
    store: CommerceStore,
    tenant_id: UUID,
    report_id: str,
    *,
    period: str | None,
    date_from: str | None,
    date_to: str | None,
    now: datetime,
) -> int:
    """Period counts from the same Contabilidad queries the download engines use."""
    from factory_os.domain.chart_accounts import ensure_chart_seed
    from factory_os.domain.journal import filter_journal_entries
    from factory_os.domain.journal_reports import balance_sheet, general_ledger, trial_balance
    from factory_os.domain.ledger import sync_facts
    from factory_os.domain.ledger_query import filter_ledger_entries, resolve_ledger_period

    sync_facts(store, tenant_id)
    ensure_chart_seed(store, tenant_id)
    day_from, day_to, _preset = resolve_ledger_period(
        period,
        date_from,
        date_to,
        now=now,
    )
    if report_id == "ledger_hechos":
        return len(
            filter_ledger_entries(
                store.list_ledger(tenant_id),
                date_from=day_from,
                date_to=day_to,
            )
        )

    entries = filter_journal_entries(
        store.list_journal_entries(tenant_id),
        date_from=day_from,
        date_to=day_to,
    )
    accounts = store.list_chart_accounts(tenant_id)
    if report_id == "journal":
        return len(entries)
    if report_id == "mayor":
        mayor = general_ledger(entries, accounts)
        return sum(len(account.get("lines") or []) for account in mayor.get("accounts") or [])
    if report_id == "comprobacion":
        return len(trial_balance(entries, accounts).get("rows") or [])
    if report_id == "resultado":
        return len(entries)
    if report_id == "balance":
        return len(balance_sheet(entries, accounts).get("rows") or [])
    raise ValueError("unknown_report")


def _download_paths(
    report_id: str,
    *,
    period: str | None,
    date_from: str | None,
    date_to: str | None,
) -> dict[str, str]:
    from urllib.parse import urlencode

    params: list[tuple[str, str]] = []
    if period and period.strip():
        params.append(("period", period.strip()))
    if date_from and date_from.strip():
        params.append(("date_from", date_from.strip()))
    if date_to and date_to.strip():
        params.append(("date_to", date_to.strip()))
    query = f"?{urlencode(params)}" if params else ""
    return {
        "csv": f"/api/reports/{report_id}.csv{query}",
        "xlsx": f"/api/reports/{report_id}.xlsx{query}",
    }


def _accounting_download_paths(
    report_id: str,
    *,
    period: str | None,
    date_from: str | None,
    date_to: str | None,
) -> dict[str, str]:
    """Point Descargas cards at Contabilidad export endpoints (same engines as /ledger)."""
    from urllib.parse import urlencode

    spec = _ACCOUNTING_DOWNLOAD_SPEC.get(report_id)
    if spec is None:
        raise ValueError("unknown_report")
    path, formats = spec
    params: list[tuple[str, str]] = []
    if date_from and date_to:
        params.append(("from", date_from))
        params.append(("to", date_to))
    elif period and period.strip():
        params.append(("period", period.strip()))
    else:
        params.append(("period", "month"))

    downloads: dict[str, str] = {}
    for key, format_value in formats.items():
        query = urlencode([*params, ("format", format_value)])
        downloads[key] = f"{path}?{query}"
    return downloads


REPORT_SHEETS: dict[str, str] = {
    "orders": "Ventas",
    "payments": "Cobros",
    "stock": "Inventario",
}


def package_window(
    *,
    month: str | None,
    period: str | None,
    now: datetime,
) -> tuple[datetime, datetime, str]:
    """Full La Paz month for ``month=YYYY-MM``, or the elapsed month for ``period=month``."""
    from factory_os.domain.analytics import BUSINESS_TZ

    raw_month = (month or "").strip()
    if raw_month:
        parts = raw_month.split("-")
        if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
            raise ValueError("bad_period")
        try:
            year = int(parts[0])
            mon = int(parts[1])
        except ValueError as exc:
            raise ValueError("bad_period") from exc
        if mon < 1 or mon > 12:
            raise ValueError("bad_period")
        start_local = datetime(year, mon, 1, tzinfo=BUSINESS_TZ)
        end_local = (
            datetime(year + 1, 1, 1, tzinfo=BUSINESS_TZ)
            if mon == 12
            else datetime(year, mon + 1, 1, tzinfo=BUSINESS_TZ)
        )
        label = f"{year:04d}-{mon:02d}"
        return start_local.astimezone(UTC), end_local.astimezone(UTC), label
    period_id = (period or "month").strip().lower()
    if period_id != "month":
        raise ValueError("bad_period")
    window = report_window("month", now=now)
    if window is None:
        raise ValueError("bad_period")
    start, end = window
    label = start.astimezone(BUSINESS_TZ).strftime("%Y-%m")
    return start, end, label


def build_package_files(
    store: CommerceStore,
    tenant_id: UUID,
    *,
    month: str | None,
    period: str | None,
    now: datetime | None = None,
) -> tuple[str, datetime, datetime, list[tuple[str, str]]]:
    """Month label, window, and CSV parts named ``YYYY-MM-orders.csv`` and siblings."""
    moment = now if now is not None else datetime.now(UTC)
    start, end, label = package_window(month=month, period=period, now=moment)
    files = [
        (f"{label}-orders.csv", orders_csv(store, tenant_id, start=start, end=end)),
        (f"{label}-payments.csv", payments_csv(store, tenant_id, start=start, end=end)),
        (f"{label}-stock.csv", stock_csv(store, tenant_id, start=start, end=end)),
    ]
    return label, start, end, files


def package_zip(files: list[tuple[str, str]]) -> bytes:
    import zipfile

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, text in files:
            archive.writestr(name, text)
    return buffer.getvalue()


def rows_to_xlsx(sheets: list[tuple[str, str]]) -> bytes:
    from openpyxl import Workbook

    book = Workbook()
    for index, (title, text) in enumerate(sheets):
        sheet = book.active if index == 0 else book.create_sheet(title[:31])
        sheet.title = title[:31]
        for row in csv.reader(StringIO(text)):
            sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def package_xlsx(files: list[tuple[str, str]]) -> bytes:
    sheets: list[tuple[str, str]] = []
    for name, text in files:
        kind = name.rsplit("-", 1)[-1].removesuffix(".csv")
        sheets.append((REPORT_SHEETS.get(kind, kind), text))
    return rows_to_xlsx(sheets)


def download_public(row: Any) -> dict[str, Any]:
    def _iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        return _as_utc(value).isoformat()

    actor_id = getattr(row, "actor_user_id", None)
    return {
        "id": str(row.id),
        "report_id": row.report_id,
        "period_id": row.period_id or "",
        "date_from": _iso(row.date_from),
        "date_to": _iso(row.date_to),
        "format": row.format,
        "actor_name": row.actor_name,
        "actor_user_id": str(actor_id) if actor_id else None,
        "created_at": _iso(row.created_at),
    }


_NOTICE_RANK = {"collections": 0, "follow_up": 1, "repurchase": 2}


_PAYMENT_STATUS_LABELS: dict[PaymentStatus, str] = {
    PaymentStatus.EXPIRED: "Vencido",
    PaymentStatus.PENDING: "Pendiente",
    PaymentStatus.CONFIRMED: "Confirmado",
    PaymentStatus.FAILED: "Fallido",
    PaymentStatus.UNKNOWN: "Desconocido",
}


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _elapsed_days(start: datetime | None, now: datetime) -> int:
    if start is None:
        return 0
    delta = _as_utc(now) - _as_utc(start)
    if delta.total_seconds() < 0:
        return 0
    return delta.days


def _relative_es(seen: datetime, now: datetime) -> str:
    days = _elapsed_days(seen, now)
    if days <= 0:
        return "hoy"
    if days == 1:
        return "hace 1 día"
    return f"hace {days} días"


def _person_label(name: str | None, fallback: str) -> str:
    cleaned = (name or "").strip()
    if cleaned:
        return cleaned
    return (fallback or "").strip()


def _order_label(order: Any) -> str:
    number = (getattr(order, "public_number", None) or "").strip()
    if number:
        return number
    return f"Pedido {str(order.id)[:8]}"


def _order_href(order: Any | None, order_id: UUID | None) -> str:
    if order is None and order_id is None:
        return "/orders"
    if order is not None:
        number = (getattr(order, "public_number", None) or "").strip()
        needle = number or str(order.id)
    else:
        needle = str(order_id)
    return "/orders?q=" + quote(needle, safe="")


def _customer_for_payment(
    payment: Payment,
    order: Any | None,
    customers_by_id: dict[UUID, Any],
) -> Any | None:
    customer_id = payment.customer_id
    if customer_id is None and order is not None:
        customer_id = order.customer_id
    if customer_id is None:
        return None
    return customers_by_id.get(customer_id)


def _overdue_row(
    payment: Payment,
    orders_by_id: dict[UUID, Any],
    customers_by_id: dict[UUID, Any],
    now: datetime,
) -> dict[str, Any]:
    order = orders_by_id.get(payment.order_id) if payment.order_id is not None else None
    customer = _customer_for_payment(payment, order, customers_by_id)
    customer_id = customer.id if customer is not None else payment.customer_id
    if order is not None:
        order_label = _order_label(order)
    elif payment.order_id is not None:
        order_label = f"Pedido {str(payment.order_id)[:8]}"
    else:
        ref = (payment.provider_ref or "").strip()
        order_label = ref or f"Pago {str(payment.id)[:8]}"
    customer_label = _person_label(
        getattr(customer, "name", None) if customer is not None else None,
        getattr(customer, "wa_number", "") if customer is not None else "",
    )
    if not customer_label:
        customer_label = "Sin cliente"
    return {
        "id": str(payment.id),
        "provider_ref": payment.provider_ref,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "status": payment.status.value,
        "status_label": _PAYMENT_STATUS_LABELS.get(payment.status, payment.status.value),
        "order_id": str(payment.order_id) if payment.order_id is not None else None,
        "order_label": order_label,
        "customer_id": str(customer_id or ""),
        "customer_label": customer_label,
        "overdue_days": _elapsed_days(payment.created_at, now),
        "href_open": _order_href(order, payment.order_id),
    }


def _conversation_at(conversations: list[Any], customer_id: UUID, seen: datetime) -> Any | None:
    target = _as_utc(seen)
    match = None
    for conversation in conversations:
        if conversation.customer_id != customer_id or conversation.last_message_at is None:
            continue
        if _as_utc(conversation.last_message_at) == target:
            match = conversation
    return match


def _inactive_row(
    customer: Any,
    seen: datetime,
    conversations: list[Any],
    now: datetime,
    inactive_days: int,
) -> dict[str, Any]:
    conversation = _conversation_at(conversations, customer.id, seen)
    name = customer.name or ""
    return {
        "id": str(customer.id),
        "name": name if name.strip() else "",
        "wa_number": customer.wa_number,
        "display_name": _person_label(name, customer.wa_number),
        "last_message_at": seen.isoformat(),
        "last_message_relative": _relative_es(seen, now),
        "inactive_days": inactive_days,
        "conversation_id": str(conversation.id) if conversation is not None else None,
        "href_open": (
            f"/chats/{conversation.id}"
            if conversation is not None
            else f"/customers/{customer.id}"
        ),
    }


def alert_payload(store: CommerceStore, tenant_id: UUID, now: datetime) -> dict[str, Any]:
    store.require_tenant(tenant_id)
    after = inactive_after_for(store, tenant_id)
    customers = store.list_customers(tenant_id)
    conversations = store.list_conversations(tenant_id)
    orders_by_id = {order.id: order for order in store.list_orders(tenant_id)}
    customers_by_id = {customer.id: customer for customer in customers}
    inactive_days = after.days
    overdue = [
        _overdue_row(payment, orders_by_id, customers_by_id, now)
        for payment in overdue_payments(store.list_payments(tenant_id))
    ]
    inactive = [
        _inactive_row(customer, seen, conversations, now, inactive_days)
        for customer, seen in inactive_customer_rows(
            customers,
            conversations,
            now,
            after=after,
        )
    ]
    return {
        "overdue_payments": overdue,
        "inactive_customers": inactive,
        "inactive_days": inactive_days,
    }


def _public(reminder: Any) -> dict[str, str]:
    return {
        "id": str(reminder.id),
        "customer_id": str(reminder.customer_id),
        "kind": reminder.kind,
        "body": reminder.body,
    }


def _deliver(store: CommerceStore, identity: Identity, channel: Any, tools: Any, reminder: Any) -> bool:
    from factory_os.harness.bbe import BBEViolation
    from factory_os.harness.policy import PolicyDenied
    from factory_os.harness.tools import PermissionDenied

    customer = store.get_customer(identity.tenant_id, reminder.customer_id)
    if customer is None:
        return False
    try:
        tools.execute(
            identity,
            "notice.send",
            {
                "customer_id": str(reminder.customer_id),
                "kind": reminder.kind,
                "body": reminder.body,
            },
            channel="whatsapp",
        )
    except (PermissionDenied, BBEViolation, PolicyDenied):
        return False
    channel.send_text(customer.wa_number, reminder.body)
    store.mark_reminder_sent(identity.tenant_id, reminder.id)
    return True


def notice_for_customer(
    store: CommerceStore,
    tenant_id: UUID,
    customer_id: UUID,
    now: datetime,
    kind: str | None = None,
) -> PlannedNotice:
    """The notice this customer would receive. Missing or inapplicable is ``no_notice``."""
    if store.get_customer(tenant_id, customer_id) is None:
        raise ValueError("no_notice")
    planned = [
        item for item in plan_notices(store, tenant_id, now) if item.customer_id == customer_id
    ]
    requested = (kind or "").strip()
    if requested:
        match = next((item for item in planned if item.kind == requested), None)
        if match is None:
            raise ValueError("no_notice")
        return match
    if not planned:
        raise ValueError("no_notice")
    planned.sort(key=lambda item: _NOTICE_RANK.get(item.kind, 9))
    return planned[0]


def preview_customer_reminder(
    store: CommerceStore,
    tenant_id: UUID,
    customer_id: UUID,
    *,
    now: datetime,
    kind: str | None = None,
) -> dict[str, Any]:
    """Read the notice text. Does not create a reminder and does not send."""
    notice = notice_for_customer(store, tenant_id, customer_id, now, kind)
    customer = store.get_customer(tenant_id, customer_id)
    if customer is None:
        raise ValueError("no_notice")
    return {
        "body": notice.body,
        "customer_label": _person_label(customer.name, customer.wa_number),
        "wa_number": customer.wa_number,
        "kind": notice.kind,
        "would_send": True,
    }


def send_customer_reminder(
    store: CommerceStore,
    tenant_id: UUID,
    channel: Any,
    tools: Any,
    *,
    customer_id: UUID,
    kind: str,
    confirm: bool,
    now: datetime,
) -> dict[str, Any]:
    """Send one notice after an explicit confirm. A notice never changes a payment."""
    if not confirm:
        raise ValueError("confirm_required")
    notice = notice_for_customer(store, tenant_id, customer_id, now, kind)
    from factory_os.contracts.employees import identity_for

    reminder = store.add_reminder(tenant_id, notice.customer_id, notice.kind, notice.body)
    identity = identity_for(SEND_ROLE[notice.kind], tenant_id)
    if not _deliver(store, identity, channel, tools, reminder):
        raise ValueError("send_failed")
    return {
        "sent": True,
        "kind": notice.kind,
        "body": notice.body,
        "customer_id": str(notice.customer_id),
    }
