"""One WhatsApp digest per America/La_Paz day for the shop owner.

The daily cron is an external HTTP call to ``POST /api/analytics/digest/run``.
This module does not use ``notice.send`` and does not write to customers.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from factory_os.domain.analytics import BUSINESS_TZ, build_analytics_summary
from factory_os.domain.store import CommerceStore


def format_analytics_digest(summary: dict[str, Any]) -> str:
    """Spanish owner text: active alert types, counts, and panel paths."""
    alerts = list(summary.get("alerts") or [])
    type_count = int(summary.get("alert_type_count") or len(alerts))
    lines = [
        "Closet: resumen de alertas (últimos 7 días).",
        f"Tipos activos: {type_count}.",
    ]
    for alert in alerts:
        label = str(alert.get("label") or alert.get("type") or "Alerta")
        count = int(alert.get("count") or 0)
        href = str(alert.get("href") or "")
        lines.append(f"- {label}: {count} → {href}")
    kpis = {str(item.get("id")): item for item in summary.get("kpis") or []}
    bits: list[str] = []
    revenue = kpis.get("revenue")
    sales = kpis.get("sales")
    if revenue is not None:
        bits.append(f"Ingresos {revenue.get('current')} BOB")
    if sales is not None:
        bits.append(f"Ventas {sales.get('current')}")
    if bits:
        lines.append(" · ".join(bits))
    return "\n".join(lines)


def run_owner_analytics_digest(
    store: CommerceStore,
    tenant_id: UUID,
    channel: Any,
    owner_numbers: list[str],
    *,
    now: datetime,
    force: bool = False,
) -> dict[str, Any]:
    """Send the 7d typed-alert digest, or skip when the day has nothing to say.

    ``force`` bypasses the opt-in flag and the once-per-day record so a person
    can send the same summary again. An empty alert list still does not send.
    """
    thresholds = store.get_analytics_thresholds(tenant_id)
    if not thresholds.digest_whatsapp_enabled and not force:
        return {"status": "disabled", "sent": 0, "reason": "disabled"}

    summary = build_analytics_summary(store, tenant_id, period="7d", now=now)
    alerts = list(summary.get("alerts") or [])
    if not alerts:
        return {"status": "no_alerts", "sent": 0, "reason": "no_alerts"}

    business_day = _business_date(now)
    if not force and store.analytics_digest_sent(tenant_id, business_day):
        return {
            "status": "skipped",
            "sent": 0,
            "reason": "already_sent",
            "alert_type_count": len(alerts),
        }

    text = format_analytics_digest(summary)
    from factory_os.tools.channel import send_text_to_owners

    sent = send_text_to_owners(channel, owner_numbers, text)
    if sent:
        store.record_analytics_digest(
            tenant_id,
            business_day,
            len(alerts),
            _as_utc(now),
        )
        return {
            "status": "sent",
            "sent": sent,
            "alert_type_count": len(alerts),
            "text_preview": text,
        }
    return {
        "status": "unsent",
        "sent": 0,
        "reason": "no_delivery",
        "alert_type_count": len(alerts),
        "text_preview": text,
    }


def _business_date(now: datetime) -> date:
    return _as_utc(now).astimezone(BUSINESS_TZ).date()


def _as_utc(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)
