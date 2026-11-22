"""WhatsApp turn graph follows the tenant's enabled modules."""

from __future__ import annotations

from uuid import uuid4

from factory_os.agents.graph import build_turn_graph, clear_turn_graphs, get_turn_graph
from factory_os.agents.orchestrator import choose_employee
from factory_os.agents.turn import ShopRuntime
from factory_os.domain.models import EmployeeRole, PILOT_TENANT_ID
from factory_os.domain.store import MemoryCommerceStore
from factory_os.domain.tenant_config import clear_memory_tenant_configs, put_tenant_config
from factory_os.domain.turn_modules import ALL_CUSTOMER_NODES, graph_nodes_for_modules
from factory_os.harness.model_gateway import FakeGateway
from tests.conftest import make_shop


def _hit(store, sku: str) -> dict:
    record = store.get_variant(PILOT_TENANT_ID, sku)
    assert record is not None
    return {
        "variant_sku": record.variant_sku,
        "codigo": record.product_sku,
        "name": record.name,
        "price": str(record.price),
        "currency": record.currency,
        "stock": record.stock,
    }


def test_empty_modules_unlock_full_customer_graph() -> None:
    assert graph_nodes_for_modules(None) == ALL_CUSTOMER_NODES
    assert graph_nodes_for_modules(()) == ALL_CUSTOMER_NODES
    assert graph_nodes_for_modules([]) == ALL_CUSTOMER_NODES


def test_whatsapp_without_cobros_drops_payment_nodes() -> None:
    nodes = graph_nodes_for_modules(("whatsapp", "pedido", "catalogo"))
    assert nodes == frozenset({"adri", "postventa"})
    assert "cobros" not in nodes
    assert "operaciones" not in nodes


def test_cobros_module_unlocks_payment_and_ops() -> None:
    nodes = graph_nodes_for_modules(("whatsapp", "cobros"))
    assert nodes == frozenset({"adri", "postventa", "cobros", "operaciones"})


def test_build_turn_graph_omits_cobros_node_when_disabled() -> None:
    clear_turn_graphs()
    graph = build_turn_graph(frozenset({"adri", "postventa"}))
    names = set(graph.get_graph().nodes)
    assert "adri" in names
    assert "postventa" in names
    assert "cobros" not in names
    assert "operaciones" not in names


def test_orchestrator_does_not_route_to_disabled_cobros() -> None:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    customer = store.get_or_create_customer(PILOT_TENANT_ID, "5918111")
    conv = store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    conv.state.order_id = uuid4()
    conv.state.chat_resolution = "wait_qr"
    allowed = frozenset({"adri", "postventa"})
    role = choose_employee(
        store,
        conv,
        "ya pagué",
        proposed=EmployeeRole.COBROS,
        allowed_nodes=allowed,
    )
    assert role is EmployeeRole.SALES


def test_run_customer_turn_respects_tenant_modules() -> None:
    clear_memory_tenant_configs()
    clear_turn_graphs()
    try:
        put_tenant_config(
            PILOT_TENANT_ID,
            industry="closet",
            modules=("whatsapp", "pedido", "catalogo"),
            name="No Cobros Shop",
        )
        store = MemoryCommerceStore(PILOT_TENANT_ID)
        runtime = ShopRuntime(store, gateway=FakeGateway())
        wa = "59181120001"
        result = runtime.handle_turn(PILOT_TENANT_ID, wa, "hola")
        assert result.role == "sales"
        conv = store.get_or_create_conversation(
            PILOT_TENANT_ID, store.get_or_create_customer(PILOT_TENANT_ID, wa)
        )
        assert conv.state.graph_node == "adri"
        conv.state.chat_resolution = "wait_qr"
        conv.state.order_id = uuid4()
        store.save_conversation_state(conv)
        again = runtime.handle_turn(PILOT_TENANT_ID, wa, "ya pagué")
        assert again.role == "sales"
        assert conv.state.graph_node == "adri"
    finally:
        clear_memory_tenant_configs()
        clear_turn_graphs()


def test_adri_to_cobros_chain_when_cobros_module_on() -> None:
    clear_memory_tenant_configs()
    clear_turn_graphs()
    try:
        put_tenant_config(
            PILOT_TENANT_ID,
            industry="closet",
            modules=("whatsapp", "pedido", "cobros", "catalogo"),
            name="With Cobros",
        )
        runtime = make_shop()
        store = runtime.store
        wa = "59181130001"
        customer = store.get_or_create_customer(PILOT_TENANT_ID, wa)
        conv = store.get_or_create_conversation(PILOT_TENANT_ID, customer)
        hit = _hit(store, "pago1-U-B")
        conv.state.considered_variant_sku = str(hit["variant_sku"])
        conv.state.last_hits = [hit]
        store.save_conversation_state(conv)

        result = runtime.handle_turn(PILOT_TENANT_ID, wa, "me lo llevo")
        conv = store.get_conversation(PILOT_TENANT_ID, conv.id)
        assert conv is not None
        assert conv.state.order_id is not None
        assert conv.state.graph_node == "cobros"
        assert result.role == "collections"
        payment = store.payment_for_order(PILOT_TENANT_ID, conv.state.order_id)
        assert payment is not None
        assert payment.provider_ref
    finally:
        clear_memory_tenant_configs()
        clear_turn_graphs()


def test_get_turn_graph_caches_by_node_set() -> None:
    clear_turn_graphs()
    a = get_turn_graph(frozenset({"adri", "postventa"}))
    b = get_turn_graph(frozenset({"adri", "postventa"}))
    c = get_turn_graph(ALL_CUSTOMER_NODES)
    assert a is b
    assert a is not c
