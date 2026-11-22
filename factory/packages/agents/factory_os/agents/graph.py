"""Short business graph (ADR-004). thread_id = conversation_id.

Durable step lives on WorkingState.graph_node in Postgres.
LangGraph InMemorySaver covers in-process invoke; pytest uses the same.

The employee nodes on the graph come from the tenant's enabled modules
(``graph_nodes_for_modules``). Empty modules keep the full customer graph.
"""

from __future__ import annotations

from typing import Any, TypedDict
from uuid import UUID

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from factory_os.agents.cobros import handle_cobros
from factory_os.agents.ops import handle_ops
from factory_os.agents.orchestrator import (
    GRAPH_NODE_BY_ROLE,
    choose_employee,
    parse_who_role,
)
from factory_os.agents.postventa import handle_postventa
from factory_os.agents.sales import handle_sales
from factory_os.contracts.employees import Identity, identity_for
from factory_os.domain.models import Conversation, Customer, EmployeeRole
from factory_os.domain.store import CommerceStore
from factory_os.domain.turn_modules import ALL_CUSTOMER_NODES, graph_nodes_for_tenant
from factory_os.harness.context import compile_context
from factory_os.harness.model_gateway import ModelGateway
from factory_os.harness.tools import ToolRuntime

_MEMORY = MemorySaver()
_GRAPHS: dict[frozenset[str], Any] = {}


class TurnGraphState(TypedDict, total=False):
    text: str
    wa_number: str
    tenant_id: str
    role: str
    graph_node: str
    reply: str
    who_source: str
    chain_cobros: bool


def _ctx() -> dict[str, Any]:
    """Per-invoke bag: store, tools, gateway, conversation, customer, trace."""
    return _INVOKE_CTX


_INVOKE_CTX: dict[str, Any] = {}


def _allowed_nodes() -> frozenset[str]:
    raw = _ctx().get("allowed_nodes")
    if isinstance(raw, frozenset):
        return raw
    return ALL_CUSTOMER_NODES


def _orchestrator_node(state: TurnGraphState) -> TurnGraphState:
    bag = _ctx()
    store: CommerceStore = bag["store"]
    conversation: Conversation = bag["conversation"]
    gateway: ModelGateway = bag["gateway"]
    text = state["text"]
    tenant_id = UUID(state["tenant_id"])
    allowed = _allowed_nodes()

    identity_probe = identity_for(EmployeeRole.SALES, tenant_id)
    context = compile_context(
        identity_probe, conversation, store=store, customer=bag.get("customer")
    )
    from factory_os.domain.tenant_employees import list_employees

    roster_bits = []
    for row in list_employees(tenant_id):
        if not row.enabled:
            continue
        hint = f", style={row.style}" if row.style else ""
        roster_bits.append(f"{row.display_name} [{row.base_role.value}]{hint}")
    if roster_bits:
        context = f"{context}\nActive roster: {'; '.join(roster_bits)}"
    propose_who = getattr(gateway, "propose_who", None)
    proposed_raw = (
        propose_who(context=context, text=text, state=conversation.state)
        if callable(propose_who)
        else None
    )
    proposed = parse_who_role(proposed_raw)
    role = choose_employee(
        store,
        conversation,
        text,
        proposed=proposed,
        allowed_nodes=allowed,
        tenant_id=tenant_id,
    )
    node = GRAPH_NODE_BY_ROLE.get(role, "adri")
    if node not in allowed:
        node = "adri" if "adri" in allowed else next(iter(sorted(allowed)))
        role = next(
            (item for item, graph_node in GRAPH_NODE_BY_ROLE.items() if graph_node == node),
            EmployeeRole.SALES,
        )
    who_source = "llm_who" if proposed is not None else "rules_fallback"
    if bag.get("trace") is not None:
        bag["trace"].record(
            "who_decision",
            parsed_action=role.value,
            provider=getattr(gateway, "last_event", {}).get("provider"),
            payload={
                "proposed": proposed.value if proposed else None,
                "authorized": role.value,
                "graph_node": node,
                "who_source": who_source,
                "allowed_nodes": sorted(allowed),
                "client_text": text,
            },
        )
    return {
        "role": role.value,
        "graph_node": node,
        "who_source": who_source,
    }


def _route_employee(state: TurnGraphState) -> str:
    node = state.get("graph_node") or "adri"
    allowed = _allowed_nodes()
    if node not in allowed:
        return "adri" if "adri" in allowed else next(iter(sorted(allowed)))
    return node


def _after_adri(state: TurnGraphState) -> str:
    """Same turn: if Adri just handed a garment to Cobros, the QR is issued now."""
    if state.get("chain_cobros") and "cobros" in _allowed_nodes():
        return "cobros"
    return "end"


def _run_adri(state: TurnGraphState) -> TurnGraphState:
    out = _employee_reply(state, EmployeeRole.SALES)
    bag = _ctx()
    conversation: Conversation = bag["conversation"]
    state_ws = conversation.state
    out["chain_cobros"] = bool(
        "cobros" in _allowed_nodes()
        and state_ws.provider_ref is None
        and state_ws.handoff is EmployeeRole.COBROS
        and (state_ws.order_id is not None or state_ws.considered_variant_sku or state_ws.cart)
    )
    return out


def _run_cobros(state: TurnGraphState) -> TurnGraphState:
    # Only merge Adri's order line when Cobros runs in the SAME turn (not a stale checkpoint reply).
    prior = str(state.get("reply") or "") if state.get("chain_cobros") else ""
    out = _employee_reply(state, EmployeeRole.COBROS)
    cobros_reply = str(out.get("reply") or "")
    if prior and cobros_reply and prior not in cobros_reply:
        out["reply"] = f"{prior}\n\n{cobros_reply}"
    out["chain_cobros"] = False
    return out


def _run_ops(state: TurnGraphState) -> TurnGraphState:
    return _employee_reply(state, EmployeeRole.OPS)


def _run_postventa(state: TurnGraphState) -> TurnGraphState:
    return _employee_reply(state, EmployeeRole.POSTVENTA)


def _employee_reply(state: TurnGraphState, role: EmployeeRole) -> TurnGraphState:
    bag = _ctx()
    conversation: Conversation = bag["conversation"]
    customer: Customer = bag["customer"]
    tools: ToolRuntime = bag["tools"]
    gateway: ModelGateway = bag["gateway"]
    tenant_id = UUID(state["tenant_id"])
    identity: Identity = identity_for(role, tenant_id)
    text = state["text"]
    wa_number = state["wa_number"]

    if role is EmployeeRole.SALES:
        reply = handle_sales(
            identity, tools, conversation, customer.id, text, gateway, store=bag["store"]
        )
    elif role is EmployeeRole.COBROS:
        reply = handle_cobros(
            identity, tools, conversation, gateway, text=text, store=bag["store"]
        )
    elif role is EmployeeRole.OPS:
        reply = handle_ops(
            identity, tools, conversation, wa_number, text, gateway, store=bag["store"]
        )
    else:
        reply = handle_postventa(identity, tools, conversation, text, gateway)

    node = GRAPH_NODE_BY_ROLE.get(role, "adri")
    conversation.state.graph_node = node
    conversation.state.last_employee = role
    return {"reply": reply, "role": role.value, "graph_node": node}


def build_turn_graph(enabled_nodes: frozenset[str] | None = None):
    """Compile a turn graph with only the employee nodes this business unlocks."""
    nodes = frozenset(enabled_nodes or ALL_CUSTOMER_NODES)
    if not nodes:
        nodes = frozenset({"adri"})
    builder = StateGraph(TurnGraphState)
    builder.add_node("orchestrator", _orchestrator_node)
    routes: dict[str, str] = {}
    if "adri" in nodes:
        builder.add_node("adri", _run_adri)
        routes["adri"] = "adri"
    if "cobros" in nodes:
        builder.add_node("cobros", _run_cobros)
        routes["cobros"] = "cobros"
    if "operaciones" in nodes:
        builder.add_node("operaciones", _run_ops)
        routes["operaciones"] = "operaciones"
    if "postventa" in nodes:
        builder.add_node("postventa", _run_postventa)
        routes["postventa"] = "postventa"
    builder.add_edge(START, "orchestrator")
    builder.add_conditional_edges("orchestrator", _route_employee, routes)
    if "adri" in nodes:
        after_adri = {"end": END}
        if "cobros" in nodes:
            after_adri["cobros"] = "cobros"
        builder.add_conditional_edges("adri", _after_adri, after_adri)
    if "cobros" in nodes:
        builder.add_edge("cobros", END)
    if "operaciones" in nodes:
        builder.add_edge("operaciones", END)
    if "postventa" in nodes:
        builder.add_edge("postventa", END)
    return builder.compile(checkpointer=_MEMORY)


def get_turn_graph(enabled_nodes: frozenset[str] | None = None):
    nodes = frozenset(enabled_nodes or ALL_CUSTOMER_NODES)
    cached = _GRAPHS.get(nodes)
    if cached is None:
        cached = build_turn_graph(nodes)
        _GRAPHS[nodes] = cached
    return cached


def clear_turn_graphs() -> None:
    _GRAPHS.clear()


def run_customer_turn(
    *,
    store: CommerceStore,
    tools: ToolRuntime,
    gateway: ModelGateway,
    conversation: Conversation,
    customer: Customer,
    tenant_id: UUID,
    wa_number: str,
    text: str,
    trace=None,
    modules: tuple[str, ...] | list[str] | None = None,
    database_url: str | None = None,
) -> tuple[EmployeeRole, str]:
    """Invoke the short graph for one WhatsApp message."""
    global _INVOKE_CTX
    if modules is None:
        from factory_os.domain.tenant_config import get_tenant_config

        modules = get_tenant_config(tenant_id, url=database_url).modules
    allowed = graph_nodes_for_tenant(tenant_id, modules=modules, url=database_url)
    _INVOKE_CTX = {
        "store": store,
        "tools": tools,
        "gateway": gateway,
        "conversation": conversation,
        "customer": customer,
        "trace": trace,
        "allowed_nodes": allowed,
    }
    graph = get_turn_graph(allowed)
    thread_id = str(conversation.id)
    result = graph.invoke(
        {
            "text": text,
            "wa_number": wa_number,
            "tenant_id": str(tenant_id),
            "graph_node": conversation.state.graph_node or "",
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    role = EmployeeRole(result["role"])
    return role, str(result.get("reply") or "")
