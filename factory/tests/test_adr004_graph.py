"""ADR-004: short graph, WHO authorize, ya pagué reads status."""

from __future__ import annotations

from uuid import uuid4

from factory_os.agents.orchestrator import authorize_who, choose_employee, choose_employee_rules
from factory_os.agents.turn import ShopRuntime
from factory_os.domain.models import EmployeeRole, PILOT_TENANT_ID, Payment, PaymentStatus
from factory_os.domain.store import MemoryCommerceStore
from factory_os.harness.model_gateway import FakeGateway


def test_authorize_who_blocks_ops_without_paid() -> None:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    customer = store.get_or_create_customer(PILOT_TENANT_ID, "5917001")
    conv = store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    conv.state.order_id = uuid4()
    assert authorize_who(store, conv, EmployeeRole.OPS) is EmployeeRole.COBROS


def test_sticky_graph_node_keeps_cobros() -> None:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    customer = store.get_or_create_customer(PILOT_TENANT_ID, "5917002")
    conv = store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    conv.state.order_id = uuid4()
    conv.state.graph_node = "cobros"
    role = choose_employee_rules(store, conv, "hola otra vez")
    assert role is EmployeeRole.COBROS


def test_graph_persists_node_across_turns() -> None:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    runtime = ShopRuntime(store, gateway=FakeGateway())
    wa = "59170009901"
    first = runtime.handle_turn(PILOT_TENANT_ID, wa, "hola")
    assert first.role == "sales"
    conv = store.get_or_create_conversation(
        PILOT_TENANT_ID, store.get_or_create_customer(PILOT_TENANT_ID, wa)
    )
    assert conv.state.graph_node == "adri"
    second = runtime.handle_turn(PILOT_TENANT_ID, wa, "busco blusas")
    assert second.role == "sales"
    assert conv.state.graph_node == "adri"


def test_ya_pague_reads_pending_and_continues() -> None:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    runtime = ShopRuntime(store, gateway=FakeGateway())
    wa = "59170009902"
    customer = store.get_or_create_customer(PILOT_TENANT_ID, wa)
    conv = store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    order_id = uuid4()
    payment_id = uuid4()
    conv.state.order_id = order_id
    conv.state.payment_id = payment_id
    conv.state.provider_ref = "qr-pending-1"
    conv.state.graph_node = "cobros"
    store.payments[payment_id] = Payment(
        id=payment_id,
        tenant_id=PILOT_TENANT_ID,
        order_id=order_id,
        provider="fake",
        provider_ref="qr-pending-1",
        amount=1,
        currency="BOB",
        status=PaymentStatus.PENDING,
        qr_payload="QR:fake",
    )
    store.save_conversation_state(conv)
    result = runtime.handle_turn(PILOT_TENANT_ID, wa, "ya pagué")
    assert "confirmado por el banco" not in result.reply.lower()
    assert "pendiente" in result.reply.lower() or "no confirma" in result.reply.lower()
    # Payment still pending — customer text did not confirm.
    assert store.payments[payment_id].status is PaymentStatus.PENDING


def test_ops_denied_without_payment_stays_conversational() -> None:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    customer = store.get_or_create_customer(PILOT_TENANT_ID, "5917003")
    conv = store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    conv.state.order_id = uuid4()
    # Model proposes OPS; runtime authorizes down to Cobros.
    role = choose_employee(store, conv, "enviame ya", proposed=EmployeeRole.OPS)
    assert role is EmployeeRole.COBROS
