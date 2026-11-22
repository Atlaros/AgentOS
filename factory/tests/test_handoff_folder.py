from uuid import uuid4

from factory_os.contracts.employees import identity_for
from factory_os.domain.models import Conversation, EmployeeRole, HandoffFolder, PILOT_TENANT_ID, WorkingState
from factory_os.harness.context import compile_context
from tests.conftest import make_shop


def test_folder_json_roundtrip_and_legacy_handoff() -> None:
    order_id = uuid4()
    state = WorkingState(order_id=order_id)
    state.pass_to(
        EmployeeRole.OPS,
        from_role=EmployeeRole.COBROS,
        pending="collect_address",
        reason="payment_confirmed",
        payment_state="confirmed",
        need="blusa",
    )
    restored = WorkingState.from_json(state.to_json())
    assert restored.handoff is EmployeeRole.OPS
    assert restored.folder.from_role is EmployeeRole.COBROS
    assert restored.folder.order_id == order_id
    assert restored.folder.payment_state == "confirmed"
    assert restored.folder.pending == "collect_address"
    assert restored.folder.need == "blusa"
    assert restored.pending_action == "collect_address"

    legacy = WorkingState.from_json(
        {"handoff": "collections", "order_id": str(order_id), "pending_action": "issue_qr"}
    )
    assert legacy.handoff is EmployeeRole.COBROS
    assert legacy.folder.pending == "issue_qr"
    assert legacy.folder.order_id == order_id


def test_folder_follows_cobros_to_ops_without_changing_who() -> None:
    shop = make_shop()
    wa = "59180000030"
    shop.handle_turn(shop.store.tenant_id, wa, "quiero una blusa de seda")
    close = shop.handle_turn(shop.store.tenant_id, wa, "confirmo")
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    # Same-turn Adri→Cobros: order + QR in one reply.
    assert "Pedido creado" in close.reply or close.employee == "Cobros"
    assert conv.state.folder.to is EmployeeRole.COBROS
    assert conv.state.folder.payment_state == "pending"
    assert conv.state.folder.pending == "wait_adapter"
    assert conv.state.folder.reason == "qr_issued"
    assert conv.state.folder.order_id == conv.state.order_id
    assert conv.state.provider_ref

    pending = shop.handle_turn(shop.store.tenant_id, wa, "ya pagué")
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert pending.employee == "Cobros"
    assert conv.state.folder.payment_state == "pending"
    assert conv.state.folder.reason == "customer_claimed_paid"

    ref = conv.state.provider_ref
    assert ref
    shop.confirm_payment_from_adapter(ref)
    paid = shop.handle_turn(shop.store.tenant_id, wa, "ya pagué")
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert "Pago confirmado" in paid.reply
    assert conv.state.folder.to is EmployeeRole.OPS
    assert conv.state.folder.from_role is EmployeeRole.COBROS
    assert conv.state.folder.payment_state == "confirmed"
    assert conv.state.folder.pending == "collect_address"

    ship = shop.handle_turn(shop.store.tenant_id, wa, "me llamo Ana, vivo en Calle 10")
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert ship.employee == "Operaciones"
    assert conv.state.folder.reason == "delivery_registered"


def test_context_includes_folder_facts() -> None:
    identity = identity_for(EmployeeRole.OPS, PILOT_TENANT_ID)
    conv = Conversation(id=uuid4(), tenant_id=PILOT_TENANT_ID, customer_id=uuid4())
    conv.state.order_id = uuid4()
    conv.state.folder = HandoffFolder(
        to=EmployeeRole.OPS,
        from_role=EmployeeRole.COBROS,
        payment_state="confirmed",
        pending="collect_address",
        reason="payment_confirmed",
    )
    text = compile_context(identity, conv)
    assert "folder=" in text
    assert "collect_address" in text
    assert "payment=confirmed" in text
    assert "role=ops" in text
