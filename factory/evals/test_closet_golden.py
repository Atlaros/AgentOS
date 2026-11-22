import re

from factory_os.domain.models import EmployeeRole
from tests.conftest import make_shop

WA = "59170000000"


def test_closet_vertical_golden() -> None:
    shop = make_shop()

    browse = shop.handle_turn(shop.store.tenant_id, WA, "quiero una blusa de seda")
    assert browse.employee == "Adri"
    assert "seda" in browse.reply.lower() or "blusa" in browse.reply.lower()
    assert "BOB" in browse.reply or "bs" in browse.reply.lower()

    # Same-turn: confirmo → pedido + QR de Cobros.
    close = shop.handle_turn(shop.store.tenant_id, WA, "confirmo")
    assert "Te paso con Cobros para el QR" in close.reply
    assert "Cobros" in close.reply or "Para pagar" in close.reply
    assert "QR:" in close.reply or "pagar" in close.reply.lower()
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    ref = conv.state.provider_ref
    assert ref
    if "QR:" in close.reply:
        match = re.search(r"QR:(pay-[a-z0-9-]+):", close.reply)
        if match:
            ref = match.group(1)

    still_pending = shop.handle_turn(shop.store.tenant_id, WA, "ya pagué")
    assert still_pending.employee == "Cobros"
    assert "pendiente" in still_pending.reply.lower()

    shop.confirm_payment_from_adapter(ref)

    paid = shop.handle_turn(shop.store.tenant_id, WA, "ya pagué")
    assert "Pago confirmado" in paid.reply
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert conv.state.folder.to is EmployeeRole.OPS
    assert conv.state.folder.payment_state == "confirmed"
    assert conv.state.folder.pending == "collect_address"
    assert conv.state.folder.order_id == conv.state.order_id
    assert conv.state.folder.reason == "payment_confirmed"

    ship = shop.handle_turn(shop.store.tenant_id, WA, "me llamo Ana, vivo en Calle 10")
    assert ship.employee == "Operaciones"
    assert "Envío registrado" in ship.reply
    assert "Ana" in ship.reply
    assert "#" in ship.reply or "pedido" in ship.reply.lower()
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert conv.state.folder.reason == "delivery_registered"
    assert conv.state.folder.payment_state == "confirmed"
