"""Run published catalog rules against store facts (Factory phase 6).

Rules never confirm a payment. Known pairs for this slice:

- ``qr_pending`` + ``hours>N`` + ``notify_owner``
- ``stock_low`` + ``below_minimum`` + ``draft_purchase_order``
- ``owner_digest`` + ``has_alerts`` + ``notify_owner`` (analytics digest)
- ``payment_overdue`` + ``expired`` + ``notify_owner``
- ``customer_inactive`` + ``days>N`` + ``notify_owner``
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from factory_os.domain.analytics import BUSINESS_TZ, build_analytics_summary
from factory_os.domain.analytics_digest import run_owner_analytics_digest
from factory_os.domain.flow_canvas import CatalogRule, list_rules
from factory_os.domain.models import PaymentStatus
from factory_os.domain.purchase_orders import create_draft_purchase_order
from factory_os.domain.replenishment import build_replenishment
from factory_os.domain.reports import inactive_after_for, inactive_customer_rows, overdue_payments

_HOURS_RE = re.compile(r"hours\s*>\s*(\d+)", re.IGNORECASE)
_DAYS_RE = re.compile(r"days\s*>\s*(\d+)", re.IGNORECASE)
_DIGEST_PREDICATES = frozenset({"", "has_alerts", "alerts", "daily", "resumen"})
_OVERDUE_PREDICATES = frozenset({"", "expired", "overdue", "vencencido"})

# Idempotency for one process lifetime (and tests).
_FIRED: set[str] = set()
_DRAFT_KEYS: set[str] = set()


@dataclass(frozen=True)
class RuleFire:
    rule_id: UUID
    when_event: str
    then_action: str
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)


def clear_rule_runtime() -> None:
    _FIRED.clear()
    _DRAFT_KEYS.clear()


def parse_hours_threshold(predicate: str, *, default: int = 24) -> int:
    match = _HOURS_RE.search(predicate or "")
    if match is None:
        return max(1, int(default))
    return max(1, int(match.group(1)))


def parse_days_threshold(predicate: str, *, default: int = 30) -> int:
    match = _DAYS_RE.search(predicate or "")
    if match is None:
        return max(1, int(default))
    return max(1, int(match.group(1)))


def published_rules_for_tenant(
    tenant_id: UUID,
    *,
    url: str | None = None,
) -> list[CatalogRule]:
    rows = list_rules(url=url)
    return [
        rule
        for rule in rows
        if rule.status == "published"
        and (rule.tenant_id is None or rule.tenant_id == tenant_id)
    ]


def collect_rule_fires(
    store: Any,
    tenant_id: UUID,
    *,
    url: str | None = None,
    now: datetime | None = None,
) -> list[RuleFire]:
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    fires: list[RuleFire] = []
    for rule in published_rules_for_tenant(tenant_id, url=url):
        event = (rule.when_event or "").strip().lower()
        action = (rule.then_action or "").strip().lower()
        if event == "qr_pending" and action == "notify_owner":
            fires.extend(_fires_for_qr_pending(store, tenant_id, rule, moment))
        elif event == "stock_low" and action == "draft_purchase_order":
            fires.extend(_fires_for_stock_low(store, tenant_id, rule))
        elif event == "owner_digest" and action == "notify_owner":
            fires.extend(_fires_for_owner_digest(store, tenant_id, rule, moment))
        elif event == "payment_overdue" and action == "notify_owner":
            fires.extend(_fires_for_payment_overdue(store, tenant_id, rule))
        elif event == "customer_inactive" and action == "notify_owner":
            fires.extend(_fires_for_customer_inactive(store, tenant_id, rule, moment))
    return fires


def apply_rule_fires(
    store: Any,
    tenant_id: UUID,
    fires: list[RuleFire],
    *,
    channel: Any | None = None,
    owner_numbers: list[str] | tuple[str, ...] = (),
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    results: list[dict[str, Any]] = []
    for fire in fires:
        if fire.when_event.strip().lower() == "owner_digest" and fire.then_action == "notify_owner":
            results.append(
                _apply_owner_digest(
                    store,
                    tenant_id,
                    fire,
                    channel=channel,
                    owner_numbers=owner_numbers,
                    now=moment,
                )
            )
        elif fire.then_action == "notify_owner":
            results.append(
                _apply_notify_owner(
                    fire,
                    channel=channel,
                    owner_numbers=owner_numbers,
                )
            )
        elif fire.then_action == "draft_purchase_order":
            results.append(_apply_draft_purchase_order(store, tenant_id, fire))
        else:
            results.append(
                {
                    "rule_id": str(fire.rule_id),
                    "action": fire.then_action,
                    "status": "skipped",
                    "reason": "unknown_action",
                }
            )
    return results


def run_published_rules(
    store: Any,
    tenant_id: UUID,
    *,
    url: str | None = None,
    now: datetime | None = None,
    channel: Any | None = None,
    owner_numbers: list[str] | tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    fires = collect_rule_fires(store, tenant_id, url=url, now=now)
    return apply_rule_fires(
        store,
        tenant_id,
        fires,
        channel=channel,
        owner_numbers=owner_numbers,
        now=now,
    )


def _fires_for_qr_pending(
    store: Any,
    tenant_id: UUID,
    rule: CatalogRule,
    now: datetime,
) -> list[RuleFire]:
    hours = parse_hours_threshold(rule.if_threshold, default=24)
    cutoff = now - timedelta(hours=hours)
    stale: list[str] = []
    for payment in store.list_payments(tenant_id):
        if payment.status is not PaymentStatus.PENDING:
            continue
        created = payment.created_at
        if created is None:
            continue
        stamp = created if created.tzinfo is not None else created.replace(tzinfo=UTC)
        if stamp > cutoff:
            continue
        key = f"qr:{tenant_id}:{rule.id}:{payment.provider_ref}"
        if key in _FIRED:
            continue
        stale.append(payment.provider_ref)
    if not stale:
        return []
    return [
        RuleFire(
            rule_id=rule.id,
            when_event=rule.when_event,
            then_action="notify_owner",
            reason=f"qr_pending_hours>{hours}",
            payload={"provider_refs": stale, "hours": hours, "keys": [
                f"qr:{tenant_id}:{rule.id}:{ref}" for ref in stale
            ]},
        )
    ]


def _fires_for_stock_low(
    store: Any,
    tenant_id: UUID,
    rule: CatalogRule,
) -> list[RuleFire]:
    predicate = (rule.if_threshold or "").strip().lower()
    if predicate not in {"below_minimum", "below_min", "stock_low"}:
        return []
    plan = build_replenishment(store, tenant_id)
    groups = [
        group
        for group in plan.get("groups", [])
        if group.get("supplier_id") and group.get("items")
    ]
    if not groups:
        return []
    skus = sorted(
        {
            str(item["variant_sku"])
            for group in groups
            for item in group["items"]
        }
    )
    key = f"po:{tenant_id}:{rule.id}:{','.join(skus)}"
    if key in _DRAFT_KEYS:
        return []
    # Skip if an open draft already covers the same SKUs.
    try:
        existing = store.list_purchase_orders(tenant_id)
    except Exception:
        existing = []
    open_skus: set[str] = set()
    for order in existing:
        if getattr(order, "status", "") != "draft":
            continue
        for line in getattr(order, "lines", []) or []:
            sku = getattr(line, "variant_sku", None)
            if sku is None and isinstance(line, dict):
                sku = line.get("variant_sku")
            if sku:
                open_skus.add(str(sku))
    if skus and set(skus) <= open_skus:
        return []
    return [
        RuleFire(
            rule_id=rule.id,
            when_event=rule.when_event,
            then_action="draft_purchase_order",
            reason="below_minimum",
            payload={"groups": groups, "skus": skus, "key": key},
        )
    ]


def _fires_for_owner_digest(
    store: Any,
    tenant_id: UUID,
    rule: CatalogRule,
    now: datetime,
) -> list[RuleFire]:
    predicate = (rule.if_threshold or "").strip().lower()
    if predicate not in _DIGEST_PREDICATES:
        return []
    thresholds = store.get_analytics_thresholds(tenant_id)
    if not thresholds.digest_whatsapp_enabled:
        return []
    business_day = now.astimezone(BUSINESS_TZ).date()
    key = f"digest:{tenant_id}:{rule.id}:{business_day.isoformat()}"
    if key in _FIRED:
        return []
    if store.analytics_digest_sent(tenant_id, business_day):
        return []
    summary = build_analytics_summary(store, tenant_id, period="7d", now=now)
    if not list(summary.get("alerts") or []):
        return []
    return [
        RuleFire(
            rule_id=rule.id,
            when_event=rule.when_event,
            then_action="notify_owner",
            reason="owner_digest_has_alerts",
            payload={"key": key, "business_day": business_day.isoformat()},
        )
    ]


def _fires_for_payment_overdue(
    store: Any,
    tenant_id: UUID,
    rule: CatalogRule,
) -> list[RuleFire]:
    predicate = (rule.if_threshold or "").strip().lower()
    if predicate not in _OVERDUE_PREDICATES:
        return []
    refs: list[str] = []
    keys: list[str] = []
    for payment in overdue_payments(store.list_payments(tenant_id)):
        ref = str(payment.provider_ref or payment.id)
        key = f"overdue:{tenant_id}:{rule.id}:{ref}"
        if key in _FIRED:
            continue
        refs.append(ref)
        keys.append(key)
    if not refs:
        return []
    text = (
        f"Factory: {len(refs)} pago(s) vencido(s). "
        f"Refs: {', '.join(refs[:5])}"
        + ("…" if len(refs) > 5 else "")
    )
    return [
        RuleFire(
            rule_id=rule.id,
            when_event=rule.when_event,
            then_action="notify_owner",
            reason="payment_overdue_expired",
            payload={
                "provider_refs": refs,
                "keys": keys,
                "text": text,
                "event": "payment_overdue",
            },
        )
    ]


def _fires_for_customer_inactive(
    store: Any,
    tenant_id: UUID,
    rule: CatalogRule,
    now: datetime,
) -> list[RuleFire]:
    default_days = max(1, int(inactive_after_for(store, tenant_id).days or 30))
    days = parse_days_threshold(rule.if_threshold, default=default_days)
    rows = inactive_customer_rows(
        store.list_customers(tenant_id),
        store.list_conversations(tenant_id),
        now,
        after=timedelta(days=days),
    )
    wa_numbers: list[str] = []
    keys: list[str] = []
    for customer, _seen in rows:
        key = f"inactive:{tenant_id}:{rule.id}:{customer.id}"
        if key in _FIRED:
            continue
        wa = str(getattr(customer, "wa_number", None) or customer.id)
        wa_numbers.append(wa)
        keys.append(key)
    if not wa_numbers:
        return []
    text = (
        f"Factory: {len(wa_numbers)} cliente(s) inactivo(s) hace más de {days} días. "
        f"WA: {', '.join(wa_numbers[:5])}"
        + ("…" if len(wa_numbers) > 5 else "")
    )
    return [
        RuleFire(
            rule_id=rule.id,
            when_event=rule.when_event,
            then_action="notify_owner",
            reason=f"customer_inactive_days>{days}",
            payload={
                "provider_refs": wa_numbers,
                "keys": keys,
                "text": text,
                "event": "customer_inactive",
                "days": days,
            },
        )
    ]


def _apply_owner_digest(
    store: Any,
    tenant_id: UUID,
    fire: RuleFire,
    *,
    channel: Any | None,
    owner_numbers: list[str] | tuple[str, ...],
    now: datetime,
) -> dict[str, Any]:
    if channel is None:
        return {
            "rule_id": str(fire.rule_id),
            "action": "notify_owner",
            "status": "no_delivery",
            "reason": "owner_digest_no_channel",
            "event": "owner_digest",
        }
    result = run_owner_analytics_digest(
        store,
        tenant_id,
        channel,
        list(owner_numbers),
        now=now,
        force=False,
    )
    key = str(fire.payload.get("key") or "")
    status = str(result.get("status") or "")
    if key and status in {"sent", "skipped", "no_alerts"}:
        _FIRED.add(key)
    return {
        "rule_id": str(fire.rule_id),
        "action": "notify_owner",
        "status": status or "unknown",
        "reason": fire.reason,
        "event": "owner_digest",
        "sent": int(result.get("sent") or 0),
        "digest": result,
    }


def _apply_notify_owner(
    fire: RuleFire,
    *,
    channel: Any | None,
    owner_numbers: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    refs = list(fire.payload.get("provider_refs") or [])
    hours = int(fire.payload.get("hours") or 24)
    custom = str(fire.payload.get("text") or "").strip()
    text = custom or (
        f"Factory: {len(refs)} QR pendiente(s) hace más de {hours} h. "
        f"Refs: {', '.join(refs[:5])}"
        + ("…" if len(refs) > 5 else "")
    )
    sent = 0
    if channel is not None and owner_numbers:
        from factory_os.tools.channel import send_text_to_owners

        sent = send_text_to_owners(channel, list(owner_numbers), text)
    for key in fire.payload.get("keys") or []:
        _FIRED.add(str(key))
    event = str(fire.payload.get("event") or fire.when_event or "").strip().lower()
    return {
        "rule_id": str(fire.rule_id),
        "action": "notify_owner",
        "status": "ok" if sent or channel is None else "no_delivery",
        "reason": fire.reason,
        "event": event or "notify_owner",
        "notified": len(refs),
        "sent": sent,
        "text": text,
    }


def _apply_draft_purchase_order(
    store: Any,
    tenant_id: UUID,
    fire: RuleFire,
) -> dict[str, Any]:
    created_ids: list[str] = []
    for group in fire.payload.get("groups") or []:
        supplier_raw = group.get("supplier_id")
        if not supplier_raw:
            continue
        supplier_id = UUID(str(supplier_raw))
        lines = [
            {
                "variant_sku": item["variant_sku"],
                "quantity": max(1, int(item.get("suggested_qty") or 1)),
            }
            for item in group.get("items") or []
        ]
        if not lines:
            continue
        order = create_draft_purchase_order(
            store,
            tenant_id,
            supplier_id,
            lines,
            notes="rule:stock_low",
        )
        created_ids.append(str(order.id))
    key = str(fire.payload.get("key") or "")
    if key:
        _DRAFT_KEYS.add(key)
    return {
        "rule_id": str(fire.rule_id),
        "action": "draft_purchase_order",
        "status": "ok" if created_ids else "skipped",
        "reason": fire.reason,
        "purchase_order_ids": created_ids,
    }
