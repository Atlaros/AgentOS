from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from factory_os.contracts.employees import (
    BBE_BY_ROLE,
    CASH_WRITE_TOOLS,
    CATALOG_WRITE_TOOLS,
    DELIVERY_TOOLS,
    INVENTORY_WRITE_TOOLS,
    PAYMENT_TOOLS,
    PAYMENT_WRITE_TOOLS,
    SALES_WRITE_TOOLS,
    SKILLS_BY_ROLE,
    Identity,
)
from factory_os.domain.models import EmployeeRole, WorkingState

logger = logging.getLogger("factory_os.bbe")

BBE_OK = "bbe_ok"
BBE_DENY = "bbe_deny"


class BBEViolation(Exception):
    """This action does not belong to the employee. Not a permission grant."""


class SkillDenied(Exception):
    """The named skill is not this employee's, or does not plan this tool."""


@dataclass(frozen=True)
class BBEAuditEvent:
    decision: str
    role: str
    employee: str
    tenant_id: str
    tool: str
    channel: str
    reason: str | None = None


class BBEAuditLog:
    """In-memory BBE decisions. Does not store payloads or secrets."""

    def __init__(self) -> None:
        self.events: list[BBEAuditEvent] = []

    def record(self, event: BBEAuditEvent) -> None:
        self.events.append(event)
        log = logger.warning if event.decision == BBE_DENY else logger.info
        log(
            "bbe decision=%s role=%s employee=%s tool=%s channel=%s reason=%s",
            event.decision,
            event.role,
            event.employee,
            event.tool,
            event.channel,
            event.reason or "-",
        )


def _deny_reason(
    identity: Identity,
    tool_name: str,
    channel: str,
    data: dict[str, Any],
) -> tuple[str, str] | None:
    rules = BBE_BY_ROLE[identity.role]
    if "no_payment_tools" in rules and tool_name in PAYMENT_TOOLS:
        return "no_payment_tools", f"{identity.employee_name} cannot act as Cobros ({tool_name})"
    if "no_payment_write" in rules and tool_name in PAYMENT_WRITE_TOOLS:
        return "no_payment_write", f"{identity.employee_name} cannot create QR ({tool_name})"
    if "no_catalog_master_write" in rules and tool_name in CATALOG_WRITE_TOOLS:
        return "no_catalog_master_write", f"{identity.employee_name} cannot edit the master catalog"
    if "no_sales_write" in rules and tool_name in SALES_WRITE_TOOLS:
        return "no_sales_write", f"{identity.employee_name} cannot create sales writes"
    if "no_delivery_tools" in rules and tool_name in DELIVERY_TOOLS:
        return "no_delivery_tools", f"{identity.employee_name} cannot create deliveries"
    if "no_inventory_write" in rules and tool_name in INVENTORY_WRITE_TOOLS:
        return "no_inventory_write", f"{identity.employee_name} cannot adjust inventory"
    if "no_cash_write" in rules and tool_name in CASH_WRITE_TOOLS:
        return "no_cash_write", f"{identity.employee_name} cannot write the cash drawer"
    if "no_customer_whatsapp" in rules and channel == "whatsapp":
        return "no_customer_whatsapp", "Catálogo does not attend customer WhatsApp"
    if "staff_channel_only" in rules and channel == "whatsapp":
        return "staff_channel_only", f"{identity.employee_name} is staff-only"
    if "customer_text_does_not_confirm_payment" in rules and data.get("mark_paid_from_text"):
        return "customer_text_does_not_confirm_payment", "customer text does not confirm payment"
    if identity.role is EmployeeRole.CATALOG_ADMIN and channel == "whatsapp":
        return "no_customer_whatsapp", "Catálogo does not attend customer WhatsApp"
    return None


def evaluate_bbe(
    identity: Identity,
    tool_name: str,
    *,
    channel: str = "whatsapp",
    payload: dict[str, Any] | None = None,
    audit: BBEAuditLog | None = None,
) -> None:
    desk = audit if audit is not None else BBEAuditLog()
    denied = _deny_reason(identity, tool_name, channel, payload or {})
    event = BBEAuditEvent(
        decision=BBE_DENY if denied else BBE_OK,
        role=identity.role.value,
        employee=identity.employee_name,
        tenant_id=str(identity.tenant_id),
        tool=tool_name,
        channel=channel,
        reason=denied[0] if denied else None,
    )
    desk.record(event)
    if denied:
        raise BBEViolation(denied[1])


def _context_present(state: WorkingState | None, payload: dict[str, Any], key: str) -> bool:
    if key == "considered_variant_or_cart":
        return bool(state and (state.considered_variant_sku or state.cart))
    if key == "order_id":
        return bool(state and state.order_id) or bool(payload.get("order_id"))
    if key == "provider_ref":
        return bool(state and state.provider_ref) or bool(payload.get("provider_ref"))
    if key == "payment_confirmed":
        return bool(state and state.folder.payment_state == "confirmed")
    if key == "variant_sku":
        return bool(payload.get("variant_sku") or (state and state.considered_variant_sku))
    if key == "customer_need":
        return bool(state and state.customer_need)
    return True


def evaluate_skill(
    identity: Identity,
    skill_name: str | None,
    tool_name: str,
    *,
    state: WorkingState | None = None,
    payload: dict[str, Any] | None = None,
    read_only: bool = False,
) -> None:
    if not skill_name:
        return
    owned = {skill.name: skill for skill in SKILLS_BY_ROLE[identity.role]}
    skill = owned.get(skill_name)
    if skill is None:
        raise SkillDenied(f"{identity.employee_name} does not have skill {skill_name}")
    if skill.related_tools and tool_name not in skill.related_tools:
        raise SkillDenied(f"{skill_name} does not plan {tool_name}")
    if read_only or not skill.required_context:
        return
    missing = [key for key in skill.required_context if not _context_present(state, payload or {}, key)]
    if missing:
        raise SkillDenied(f"{skill_name} missing context: {', '.join(missing)}")
