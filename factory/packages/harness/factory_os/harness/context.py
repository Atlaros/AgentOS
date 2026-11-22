from __future__ import annotations

from typing import Any

from factory_os.contracts.employees import Identity
from factory_os.domain.models import Conversation, Customer
from factory_os.domain.store import CommerceStore


def compile_context(
    identity: Identity,
    conversation: Conversation,
    extra: str = "",
    *,
    store: CommerceStore | None = None,
    customer: Customer | None = None,
    prefs: dict[str, str] | None = None,
) -> str:
    """Minimum desk papers for this turn — not the whole shop."""
    from factory_os.domain.knowledge import compact_shop_card
    from factory_os.domain.memory import (
        RECENT_WINDOW,
        format_conversation_summary,
        format_customer_memory,
    )

    considered = conversation.state.considered_variant_sku or "none"
    order = str(conversation.state.order_id) if conversation.state.order_id else "none"
    state = conversation.state
    folder = state.folder
    recent = conversation.messages[-RECENT_WINDOW:]

    resolved_customer = customer
    resolved_prefs = dict(prefs or {})
    if store is not None:
        if resolved_customer is None:
            resolved_customer = store.get_customer(identity.tenant_id, conversation.customer_id)
        if not resolved_prefs:
            resolved_prefs = store.get_customer_preferences(
                identity.tenant_id, conversation.customer_id
            )
        # Merge durable working-state prefs if store empty this turn.
        from factory_os.domain.memory import prefs_from_working_state

        for key, value in prefs_from_working_state(state).items():
            resolved_prefs.setdefault(key, value)

    lines = [
        f"employee={identity.employee_name} role={identity.role.value} tenant={identity.tenant_id}",
        f"considered={considered} order={order}",
        f"stage={state.stage.value} skill={state.last_skill or 'none'} nba={state.last_action or 'none'}",
        f"graph_node={state.graph_node or 'none'}",
        (
            "folder="
            f"to={folder.to.value if folder.to else 'none'} "
            f"from={folder.from_role.value if folder.from_role else 'none'} "
            f"payment={folder.payment_state or 'none'} "
            f"pending={folder.pending or 'none'} "
            f"need={folder.need or 'none'} "
            f"reason={folder.reason or 'none'}"
        ),
        compact_shop_card(
            identity.tenant_id,
            store.get_shop_knowledge(identity.tenant_id)
            if store is not None and hasattr(store, "get_shop_knowledge")
            else None,
        ),
    ]
    memory_line = format_customer_memory(
        name=resolved_customer.name if resolved_customer else None,
        address=resolved_customer.address if resolved_customer else None,
        prefs=resolved_prefs,
    )
    if memory_line:
        lines.append(memory_line)
    summary_line = format_conversation_summary(conversation.summary_text)
    if summary_line:
        lines.append(summary_line)
    if conversation.turn_idle_reopen:
        lines.append("idle_reopen=true")
    lines.append("recent:")
    for role, text in recent:
        lines.append(f"  {role}: {text}")
    if extra:
        lines.append(extra)
    return "\n".join(lines)
