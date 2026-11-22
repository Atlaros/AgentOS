from factory_os.agents.sales import apply_stage, next_best_action
from factory_os.domain.models import ConversationStage, NextAction, WorkingState
from factory_os.harness.model_gateway import parse_proposal
from tests.conftest import make_shop


def test_search_skips_discovery_rail() -> None:
    shop = make_shop()
    result = shop.handle_turn(shop.store.tenant_id, "59180000040", "quiero una blusa de seda")
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert result.employee == "Adri"
    assert conv.state.stage is ConversationStage.RECOMMENDATION
    assert conv.state.discovery_asked is False
    assert conv.state.last_action == NextAction.SEARCH_CATALOG.value


def test_gift_need_then_need_identified_without_forcing_recommendation() -> None:
    shop = make_shop()
    first = shop.handle_turn(
        shop.store.tenant_id, "59180000041", "Necesito algo para regalarle a mi esposa."
    )
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert conv.state.stage is ConversationStage.DISCOVERY
    assert "presupuesto" in first.reply.lower()

    state = WorkingState(customer_need="regalo", discovery_asked=True)
    apply_stage(state, NextAction.SEARCH_CATALOG, "xyzqwerty-no-existe")
    assert state.stage is ConversationStage.NEED_IDENTIFIED

    miss_shop = make_shop()
    miss = miss_shop.handle_turn(miss_shop.store.tenant_id, "59180000049", "xyzqwerty-no-existe")
    cold = miss_shop.store.list_conversations(miss_shop.store.tenant_id)[0]
    assert "No encontré esa prenda" in miss.reply
    assert cold.state.stage is ConversationStage.DISCOVERY


def test_price_objection_stays_objection_without_ready_to_buy() -> None:
    state = WorkingState(considered_variant_sku="pago1-U-B", last_hits=[{"price": "1.00"}])
    action, skill = next_best_action(state, "está caro")
    assert action is NextAction.HANDLE_OBJECTION
    assert skill == "objection_handling"

    shop = make_shop()
    shop.handle_turn(shop.store.tenant_id, "59180000042", "quiero una blusa de seda")
    objection = shop.handle_turn(shop.store.tenant_id, "59180000042", "Está muy caro.")
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert conv.state.stage is ConversationStage.OBJECTION
    assert conv.state.stage is not ConversationStage.READY_TO_BUY
    assert "20%" not in objection.reply


def test_compare_and_soft_interest_are_own_actions() -> None:
    shop = make_shop()
    shop.handle_turn(shop.store.tenant_id, "59180000043", "quiero una blusa")
    shop.handle_turn(shop.store.tenant_id, "59180000043", "talla M")
    compared = shop.handle_turn(shop.store.tenant_id, "59180000043", "cuál me conviene entre esas")
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert conv.state.last_action == NextAction.COMPARE.value
    assert conv.state.stage is ConversationStage.CONSIDERATION
    assert "Comparo" in compared.reply or "catálogo" in compared.reply.lower() or "catalogo" in compared.reply.lower()

    shop.handle_turn(shop.store.tenant_id, "59180000044", "quiero una blusa de seda")
    soft = shop.handle_turn(shop.store.tenant_id, "59180000044", "me gusta esa")
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert "Pedido creado" not in soft.reply
    assert conv.state.last_action in {
        NextAction.REQUEST_CONFIRMATION.value,
        NextAction.HANDLE_OBJECTION.value,
        NextAction.SEARCH_CATALOG.value,
        NextAction.COMPARE.value,
    } or "confirmo" in soft.reply.lower() or "late" in soft.reply.lower()


def test_paid_and_postventa_write_purchased_and_post_sale() -> None:
    shop = make_shop()
    damaged = shop.handle_turn(shop.store.tenant_id, "59180000045", "Mi pedido llegó roto.")
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert damaged.employee == "Postventa"
    assert conv.state.stage is ConversationStage.POST_SALE

    shop.handle_turn(shop.store.tenant_id, "59180000046", "quiero una blusa de seda")
    close = shop.handle_turn(shop.store.tenant_id, "59180000046", "confirmo")
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert conv.state.stage is ConversationStage.CHECKOUT
    assert "QR:" in close.reply or "pagar" in close.reply.lower() or "cobros" in close.reply.lower()
    ref = conv.state.provider_ref
    assert ref
    shop.confirm_payment_from_adapter(ref)
    shop.handle_turn(shop.store.tenant_id, "59180000046", "ya pagué")
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert conv.state.stage is ConversationStage.PURCHASED


def test_parse_proposal_keeps_first_class_nba_actions() -> None:
    recommend = parse_proposal('{"action":"recommend","skill":"product_recommendation"}', "gemini")
    compare = parse_proposal('{"action":"compare","skill":"product_recommendation"}', "gemini")
    confirm = parse_proposal('{"action":"request_confirmation","skill":"sales_closing"}', "gemini")
    assert recommend is not None and recommend.action is NextAction.RECOMMEND
    assert compare is not None and compare.action is NextAction.COMPARE
    assert confirm is not None and confirm.action is NextAction.REQUEST_CONFIRMATION
    greet = parse_proposal('{"action":"greet"}', "gemini")
    assert greet is not None and greet.action is NextAction.ANSWER
