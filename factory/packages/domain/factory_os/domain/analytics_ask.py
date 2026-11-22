"""Narrative answer over Analítica facts. Numbers stay in the summary payload."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from factory_os.domain.analytics import build_analytics_summary
from factory_os.domain.store import CommerceStore

_DIGIT_RUN = re.compile(r"\d+(?:[.,]\d+)*")
_LETTER = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]")

ANALYST_SYSTEM = """\
Sos el Analista de Authentic Closet, un ayudante interno del dueño y del supervisor.
Respondé en español, en 2 a 6 oraciones.
Usá ÚNICAMENTE el JSON de FACTS. No inventes números, montos, márgenes ni porcentajes.
Si la pregunta necesita un hecho que no está en FACTS, decilo con claridad.
Cuando haya alertas, señalá el deep link (href) para ir a Proveedores, Reportes, Pedidos u otra pantalla del panel.
No confirmes pagos, no escribas stock ni asientos, y no contactes a nadie.
"""


def format_analytics_fallback(data: dict[str, Any]) -> str:
    """Deterministic staff summary. Same lines the Analista used before the narrative."""
    period = data.get("period") if isinstance(data.get("period"), dict) else {}
    lines = [
        "Resumen de Analítica (hechos del archivo, no inventados):",
        f"- Período: {period.get('id') or '7d'} ({period.get('start') or '—'} → {period.get('end') or '—'})",
        f"- Pedidos: {data.get('orders', 0)}",
        f"- Reservas: {data.get('reservations', 0)}",
        f"- Pagos confirmados: {data.get('payments_confirmed', 0)} · {data.get('confirmed_amount', '0')} BOB",
        f"- QR pendientes: {data.get('payments_pending', 0)}",
        f"- SKUs en stock bajo (umbral por producto): {data.get('low_stock_count', 0)}",
    ]
    for item in data.get("low_stock") or []:
        if not isinstance(item, dict):
            continue
        threshold = item.get("reorder_threshold")
        threshold_bit = f" · umbral {threshold}" if threshold is not None else ""
        lines.append(
            f"  · {item.get('name')} · {item.get('variant_sku')} · stock {item.get('stock')}{threshold_bit}"
        )
    alerts = data.get("alerts") or []
    if alerts:
        lines.append(f"- Alertas activas (tipos): {data.get('alert_type_count', len(alerts))}")
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            lines.append(
                f"  · {alert.get('type')}: {alert.get('count', 0)} → {alert.get('href') or '—'}"
            )
    return "\n".join(lines)


def facts_text(facts: dict[str, Any]) -> str:
    return json.dumps(facts, ensure_ascii=False, sort_keys=True, default=str)


def reply_is_grounded(text: str, facts: dict[str, Any]) -> bool:
    """Reject empty text and any digit run that is not already in the facts JSON."""
    cleaned = " ".join(text.split())
    if len(cleaned) < 12 or cleaned[:1] in "{[":
        return False
    if _LETTER.search(cleaned) is None or len(cleaned.split(" ")) < 3:
        return False
    blob = facts_text(facts)
    return all(token in blob for token in _DIGIT_RUN.findall(text))


def answer_analytics_question(
    store: CommerceStore,
    tenant_id: UUID,
    question: str,
    gateway: Any,
    *,
    period: str = "7d",
) -> dict[str, Any]:
    """One narrative call over the summary. Fake and ungrounded replies use the fallback."""
    facts = build_analytics_summary(store, tenant_id, period=period or "7d")
    fallback = format_analytics_fallback(facts)
    user = f"PREGUNTA:\n{(question or '').strip()}\n\nFACTS JSON:\n{facts_text(facts)}"
    result = gateway.staff_answer(system=ANALYST_SYSTEM, user=user, fallback=fallback)
    text = str(getattr(result, "text", "") or "").strip()
    deterministic = bool(getattr(gateway, "is_deterministic", False))
    used_flag = bool(getattr(result, "used_fallback", False))
    if deterministic or used_flag or not reply_is_grounded(text, facts):
        return {"reply": fallback, "used_fallback": True, "facts": facts}
    return {"reply": text, "used_fallback": False, "facts": facts}
