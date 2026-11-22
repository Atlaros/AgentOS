"""Owner-approved WhatsApp send for supplier purchase orders (ADR-012 amendment)."""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any
from uuid import UUID

from factory_os.domain.purchase_orders import public_number, transition_purchase_order
from factory_os.tools.channel import Channel

_SUPPLIER_NUMBER_MISSING = "supplier_number_missing"
_SEND_FAILED = "send_failed"
_TEMPLATE_SUMMARY_MAX = 900
# Meta rejects newlines inside template variables; keep {{3}} one line.
_TEMPLATE_ITEMS_MAX = 400

# Exact body Meta should approve (UTILITY). Variables: {{1}} negocio, {{2}} nº OC, {{3}} ítems.
SUPPLIER_ORDER_TEMPLATE_BODY = (
    "Hola, somos {{1}}. Pedido de compra {{2}}:\n{{3}}\n"
    "Por favor confirmen disponibilidad y tiempo de entrega. Gracias."
)
SUPPLIER_ORDER_TEMPLATE_NAME_DEFAULT = "pedido_proveedor_oc"


def _business_name() -> str:
    return (
        (os.environ.get("SHOP_NAME") or "").strip()
        or (os.environ.get("CASH_TICKET_BUSINESS_NAME") or "").strip()
        or "Nuestro negocio"
    )


def resolve_supplier_wa_number(supplier: Any) -> str:
    """Prefer whatsapp, then phone; strip spaces. Empty when neither is usable."""
    for field in ("whatsapp", "phone"):
        raw = str(getattr(supplier, field, "") or "").strip()
        if raw:
            return raw.replace(" ", "")
    return ""


def format_purchase_order_message(order_detail: dict[str, Any]) -> str:
    """Spanish plain-text OC summary for the supplier."""
    business = _business_name()
    order_ref = str(order_detail.get("number") or order_detail.get("id") or "").strip()
    short_id = order_ref.split("-")[-1] if order_ref else ""
    header = f"Pedido de compra {order_ref or short_id} — {business}"
    lines: list[str] = []
    total = Decimal("0")
    has_total = False
    for raw in order_detail.get("lines") or []:
        sku = str(raw.get("variant_sku") or "").strip()
        name = str(raw.get("name") or sku).strip()
        qty = int(raw.get("quantity_ordered") or 0)
        label = f"{sku} ({name})" if name and name != sku else sku
        lines.append(f"• {label}: {qty} u.")
        unit_cost = raw.get("unit_cost")
        if unit_cost is not None and str(unit_cost).strip() != "":
            cost = Decimal(str(unit_cost).replace(",", "."))
            total += cost * qty
            has_total = True
    body_lines = [header, "Ítems:", *lines]
    notes = str(order_detail.get("notes") or "").strip()
    if notes:
        body_lines.append(f"Notas: {notes}")
    if has_total:
        body_lines.append(f"Total estimado: {total.quantize(Decimal('0.01'))} BOB")
    return "\n".join(body_lines)


def _enrich_order_detail(store: Any, tenant_id: UUID, order: Any) -> dict[str, Any]:
    from factory_os.domain.purchase_orders import purchase_order_line_public, purchase_order_public

    payload = purchase_order_public(order)
    supplier = store.get_supplier(tenant_id, order.supplier_id)
    payload["supplier_name"] = supplier.name if supplier else ""
    enriched_lines: list[dict[str, Any]] = []
    for line in order.lines:
        row = purchase_order_line_public(line)
        variant = store.get_variant(tenant_id, line.variant_sku)
        row["name"] = variant.name if variant is not None else line.variant_sku
        enriched_lines.append(row)
    payload["lines"] = enriched_lines
    return payload


def preview_send_purchase_order(
    store: Any,
    tenant_id: UUID,
    order_id: UUID,
) -> dict[str, Any]:
    order = store.get_purchase_order(tenant_id, order_id)
    if order is None:
        raise KeyError(order_id)
    if order.status != "draft":
        raise ValueError("bad_status")
    supplier = store.get_supplier(tenant_id, order.supplier_id)
    if supplier is None:
        raise KeyError(order.supplier_id)
    detail = _enrich_order_detail(store, tenant_id, order)
    wa_number = resolve_supplier_wa_number(supplier)
    body = format_purchase_order_message(detail)
    return {
        "body": body,
        "wa_number": wa_number,
        "supplier_name": supplier.name,
        "order_id": str(order_id),
        "number": detail.get("number") or public_number(order_id),
        "can_send": bool(wa_number),
    }


def _truncate_for_template(text: str, *, max_len: int = _TEMPLATE_SUMMARY_MAX) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def template_body_parameters(order_detail: dict[str, Any]) -> list[str]:
    """Three short Meta body params: business, order number, one-line items (no newlines)."""
    business = _truncate_for_template(_business_name(), max_len=60)
    order_ref = str(order_detail.get("number") or order_detail.get("id") or "").strip()
    short = order_ref.split("-")[-1] if order_ref else "OC"
    number = _truncate_for_template(order_ref or short, max_len=40)
    parts: list[str] = []
    for raw in order_detail.get("lines") or []:
        sku = str(raw.get("variant_sku") or "").strip()
        name = str(raw.get("name") or sku).strip()
        qty = int(raw.get("quantity_ordered") or 0)
        label = name if name else sku
        parts.append(f"{label} x{qty}")
    items = _truncate_for_template(
        "; ".join(parts) if parts else "sin líneas",
        max_len=_TEMPLATE_ITEMS_MAX,
    )
    # Meta template variables cannot contain newlines.
    items = " ".join(items.split())
    return [business, number, items]


def confirm_send_purchase_order(
    store: Any,
    tenant_id: UUID,
    order_id: UUID,
    channel: Channel,
    *,
    template_name: str | None = None,
    template_lang: str = "es",
) -> dict[str, Any]:
    """Send to supplier, then transition draft→sent. Fail closed on channel errors."""
    preview = preview_send_purchase_order(store, tenant_id, order_id)
    if not preview["can_send"]:
        raise ValueError(_SUPPLIER_NUMBER_MISSING)
    wa_number = str(preview["wa_number"])
    body = str(preview["body"])
    template = (template_name or "").strip()
    order = store.get_purchase_order(tenant_id, order_id)
    if order is None:
        raise KeyError(order_id)
    detail = _enrich_order_detail(store, tenant_id, order)
    try:
        if template:
            channel.send_template(
                wa_number,
                name=template,
                language=(template_lang or "es").strip() or "es",
                body_parameters=template_body_parameters(detail),
            )
        else:
            channel.send_text(wa_number, body)
    except Exception as exc:
        raise ValueError(_SEND_FAILED) from exc
    order = transition_purchase_order(store, tenant_id, order_id, "sent")
    from factory_os.domain.purchase_orders import purchase_order_public

    return {
        "sent": True,
        "wa_number": wa_number,
        "body": body,
        "purchase_order": purchase_order_public(order),
        "template_name": template or None,
    }