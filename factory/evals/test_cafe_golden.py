"""Café template golden: catalog facts from seed; customer text never confirms payment."""

from factory_os.agents.turn import ShopRuntime
from factory_os.domain.models import PILOT_TENANT_ID, PaymentStatus
from factory_os.domain.seed import catalog_seed_path, load_catalog_json
from factory_os.domain.store import MemoryCommerceStore
from factory_os.tools.registry import FakePaymentProvider

WA = "59171110001"


def _cafe_shop() -> ShopRuntime:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(catalog_seed_path("cafe"), store)
    return ShopRuntime(store, FakePaymentProvider())


def test_cafe_browse_and_text_does_not_confirm_payment() -> None:
    shop = _cafe_shop()
    browse = shop.handle_turn(shop.store.tenant_id, WA, "quiero empanadas")
    assert browse.employee == "Adri"
    assert "empanada" in browse.reply.lower()
    assert "BOB" in browse.reply or "bs" in browse.reply.lower()

    close = shop.handle_turn(shop.store.tenant_id, WA, "confirmo")
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    ref = conv.state.provider_ref
    assert ref, "expected a payment after confirmo"

    still = shop.handle_turn(shop.store.tenant_id, WA, "ya pagué")
    assert still.employee == "Cobros"
    payment = shop.store.payment_status(shop.store.tenant_id, ref)
    assert payment is not None
    assert payment.status is PaymentStatus.PENDING

    calls: list[str] = []
    shop.settlement_notifier = lambda payment: calls.append(payment.provider_ref)

    still = shop.handle_turn(shop.store.tenant_id, WA, "ya pagué")
    assert still.employee == "Cobros"
    payment = shop.store.payment_status(shop.store.tenant_id, ref)
    assert payment is not None
    assert payment.status is PaymentStatus.PENDING
    assert calls == []

    shop.confirm_payment_from_adapter(ref)
    paid = shop.handle_turn(shop.store.tenant_id, WA, "ya pagué")
    assert "confirmado" in paid.reply.lower()
    payment = shop.store.payment_status(shop.store.tenant_id, ref)
    assert payment is not None
    assert payment.status is PaymentStatus.CONFIRMED
    assert calls == [ref]


def test_agentos_outage_does_not_undo_adapter_confirm() -> None:
    shop = _cafe_shop()

    def down(_payment) -> None:
        raise RuntimeError("agentos down")

    shop.settlement_notifier = down
    shop.handle_turn(shop.store.tenant_id, WA, "quiero empanadas")
    shop.handle_turn(shop.store.tenant_id, WA, "confirmo")
    ref = shop.store.list_conversations(shop.store.tenant_id)[0].state.provider_ref
    shop.confirm_payment_from_adapter(ref)
    payment = shop.store.payment_status(shop.store.tenant_id, ref)
    assert payment is not None
    assert payment.status is PaymentStatus.CONFIRMED
