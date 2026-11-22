"""WHO: Gemini proposes the employee; runtime authorizes the handoff.

Fallback when the model does not propose: sticky graph_node / handoff / last
employee + business facts (order, payment). Never scan customer text for keywords
to pick WHO (ADR-003 / ADR-004). FakeGateway.propose_who simulates intent in pytest.
"""

from __future__ import annotations

from factory_os.domain.models import Conversation, EmployeeRole, PaymentStatus
from factory_os.domain.seed import normalize
from factory_os.domain.store import CommerceStore

_CUSTOMER_FACING = frozenset(
    {
        EmployeeRole.SALES,
        EmployeeRole.COBROS,
        EmployeeRole.OPS,
        EmployeeRole.POSTVENTA,
    }
)

_ROLE_BY_VALUE = {role.value: role for role in _CUSTOMER_FACING}
_ROLE_BY_VALUE.update(
    {
        "adri": EmployeeRole.SALES,
        "sales": EmployeeRole.SALES,
        "cobros": EmployeeRole.COBROS,
        "collections": EmployeeRole.COBROS,
        "ops": EmployeeRole.OPS,
        "operaciones": EmployeeRole.OPS,
        "postventa": EmployeeRole.POSTVENTA,
    }
)

GRAPH_NODE_BY_ROLE = {
    EmployeeRole.SALES: "adri",
    EmployeeRole.COBROS: "cobros",
    EmployeeRole.OPS: "operaciones",
    EmployeeRole.POSTVENTA: "postventa",
}
ROLE_BY_GRAPH_NODE = {node: role for role, node in GRAPH_NODE_BY_ROLE.items()}


def _payment_confirmed(store: CommerceStore, conversation: Conversation) -> bool:
    state = conversation.state
    if state.payment_id is None:
        return False
    payment = store.get_payment(conversation.tenant_id, state.payment_id)
    return payment is not None and payment.status is PaymentStatus.CONFIRMED


def parse_who_role(raw: str | None) -> EmployeeRole | None:
    if not raw:
        return None
    key = normalize(str(raw)).replace(" ", "_")
    return _ROLE_BY_VALUE.get(key)


def authorize_who(
    store: CommerceStore,
    conversation: Conversation,
    proposed: EmployeeRole,
) -> EmployeeRole:
    """Runtime guard on WHO. Never invents payment or order facts."""
    if proposed not in _CUSTOMER_FACING:
        return EmployeeRole.SALES
    state = conversation.state
    if state.channel == "internal":
        return proposed

    has_order = state.order_id is not None
    has_qr = bool(state.provider_ref or state.payment_id)
    paid = _payment_confirmed(store, conversation)

    if proposed is EmployeeRole.OPS:
        if has_order and paid:
            return EmployeeRole.OPS
        if has_order or has_qr:
            return EmployeeRole.COBROS
        return EmployeeRole.SALES

    if proposed is EmployeeRole.COBROS:
        if has_order or has_qr:
            return EmployeeRole.COBROS
        return EmployeeRole.SALES

    if proposed is EmployeeRole.POSTVENTA:
        return EmployeeRole.POSTVENTA

    return EmployeeRole.SALES


def choose_employee_rules(store: CommerceStore, conversation: Conversation, text: str) -> EmployeeRole:
    """Deterministic WHO fallback: sticky step + folder + facts. No keyword scan of text."""
    _ = text
    state = conversation.state
    if state.channel == "internal":
        if state.last_employee in {EmployeeRole.INVENTORY, EmployeeRole.CATALOG_ADMIN}:
            return state.last_employee
        return EmployeeRole.SALES

    paid = _payment_confirmed(store, conversation)
    has_order = state.order_id is not None

    # Folder handoff after bank confirm beats a stale cobros checkpoint.
    if state.handoff is EmployeeRole.OPS and has_order and paid:
        return EmployeeRole.OPS
    if state.handoff is EmployeeRole.POSTVENTA:
        return EmployeeRole.POSTVENTA

    if state.graph_node and state.graph_node in ROLE_BY_GRAPH_NODE:
        sticky = ROLE_BY_GRAPH_NODE[state.graph_node]
        if sticky is EmployeeRole.COBROS and has_order and paid:
            return EmployeeRole.OPS
        return authorize_who(store, conversation, sticky)

    if state.handoff in _CUSTOMER_FACING:
        return authorize_who(store, conversation, state.handoff)  # type: ignore[arg-type]

    if state.last_employee in _CUSTOMER_FACING:
        return authorize_who(store, conversation, state.last_employee)

    if has_order and paid:
        return EmployeeRole.OPS
    if has_order and not paid:
        return EmployeeRole.COBROS
    return EmployeeRole.SALES


def constrain_role(
    role: EmployeeRole,
    allowed_nodes: frozenset[str] | None,
) -> EmployeeRole:
    """Drop a WHO pick whose graph node is off for this business."""
    if not allowed_nodes:
        return role
    node = GRAPH_NODE_BY_ROLE.get(role)
    if node is not None and node in allowed_nodes:
        return role
    if "adri" in allowed_nodes:
        return EmployeeRole.SALES
    for candidate, graph_node in GRAPH_NODE_BY_ROLE.items():
        if graph_node in allowed_nodes:
            return candidate
    return EmployeeRole.SALES


def constrain_roster(
    role: EmployeeRole,
    enabled_roles: frozenset[EmployeeRole] | None,
) -> EmployeeRole:
    """Drop a WHO pick whose base role is disabled on the tenant roster (ADR-026)."""
    if enabled_roles is None:
        return role
    if role in enabled_roles:
        return role
    for candidate in (
        EmployeeRole.SALES,
        EmployeeRole.COBROS,
        EmployeeRole.OPS,
        EmployeeRole.POSTVENTA,
    ):
        if candidate in enabled_roles:
            return candidate
    return EmployeeRole.SALES


def choose_employee(
    store: CommerceStore,
    conversation: Conversation,
    text: str,
    *,
    proposed: EmployeeRole | None = None,
    allowed_nodes: frozenset[str] | None = None,
    tenant_id=None,
    enabled_roles: frozenset[EmployeeRole] | None = None,
) -> EmployeeRole:
    """Authorize a model WHO proposal, else fall back to sticky/facts rules."""
    roster = enabled_roles
    if roster is None and tenant_id is not None:
        from factory_os.domain.tenant_employees import enabled_base_roles

        roster = enabled_base_roles(tenant_id)
    # A left QR stays with Cobros until the bank confirms. A WHO proposal must not rebuild it.
    if conversation.state.chat_resolution == "wait_qr" and not _payment_confirmed(store, conversation):
        return constrain_roster(constrain_role(EmployeeRole.COBROS, allowed_nodes), roster)
    # Idle reopen is Adri's job: greet + ask continue vs search other (one turn).
    if conversation.turn_idle_reopen and conversation.state.channel != "internal":
        return constrain_roster(constrain_role(EmployeeRole.SALES, allowed_nodes), roster)
    if proposed is not None:
        picked = constrain_role(authorize_who(store, conversation, proposed), allowed_nodes)
        return constrain_roster(picked, roster)
    picked = constrain_role(choose_employee_rules(store, conversation, text), allowed_nodes)
    return constrain_roster(picked, roster)
