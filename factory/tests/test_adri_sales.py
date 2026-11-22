import pytest

from factory_os.agents.sales import next_best_action
from factory_os.contracts.employees import ROLE_PERMISSIONS, identity_for
from factory_os.contracts.skills import ADRI_SKILLS, BBE_SALES
from factory_os.domain.catalog import search_catalog
from factory_os.domain.models import (
    ConversationStage,
    EmployeeRole,
    NextAction,
    PILOT_TENANT_ID,
    WorkingState,
)
from factory_os.domain.seed import extra_seed_paths, load_catalog_json, load_pilot_catalog, normalize
from factory_os.domain.store import MemoryCommerceStore
from factory_os.harness.model_gateway import ActionProposal, DraftResult
from factory_os.harness.policy import PolicyDenied
from factory_os.harness.tools import PermissionDenied
from tests.conftest import make_shop

WA = "59170001111"


def test_skills_do_not_grant_payment_permission() -> None:
    skill_names = {skill.name for skill in ADRI_SKILLS}
    assert "sales_closing" in skill_names
    assert "payment.create_qr" not in ROLE_PERMISSIONS[EmployeeRole.SALES]
    assert "skill_does_not_grant_permission" in BBE_SALES
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    assert adri.permissions == ROLE_PERMISSIONS[EmployeeRole.SALES]


def test_gift_need_asks_before_search() -> None:
    action, skill = next_best_action(WorkingState(), "Necesito algo para regalarle a mi esposa.")
    assert action is NextAction.ASK_DISCOVERY_QUESTION
    assert skill == "sales_discovery"
    shop = make_shop()
    first = shop.handle_turn(shop.store.tenant_id, WA, "Necesito algo para regalarle a mi esposa.")
    assert first.employee == "Adri"
    assert "presupuesto" in first.reply.lower()
    assert "No encontré esa prenda" not in first.reply
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert conv.state.stage is ConversationStage.DISCOVERY
    assert conv.state.discovery_asked


def test_natural_language_wedding_retrieves_real_catalog() -> None:
    shop = make_shop()
    result = shop.handle_turn(
        shop.store.tenant_id, "59170001112", "Quiero una blusa de seda elegante."
    )
    lowered = result.reply.lower()
    assert "No encontré esa prenda" not in result.reply
    assert "blusa" in lowered or "seda" in lowered or "corset" in lowered or "presupuesto" in lowered


def test_price_objection_does_not_invent_discount() -> None:
    shop = make_shop()
    shop.handle_turn(shop.store.tenant_id, "59170001113", "quiero una blusa de seda")
    objection = shop.handle_turn(shop.store.tenant_id, "59170001113", "Está muy caro.")
    lowered = objection.reply.lower()
    assert "20%" not in objection.reply
    assert "invent" in lowered or "no hay" in lowered
    assert "seda" in lowered or "stock" in lowered or "blusa" in lowered or "bs" in lowered


def test_me_llevo_ese_creates_order() -> None:
    shop = make_shop()
    shop.handle_turn(shop.store.tenant_id, "59170001114", "quiero una blusa de seda")
    close = shop.handle_turn(shop.store.tenant_id, "59170001114", "Me llevo ese.")
    assert "Te paso con Cobros para el QR" in close.reply
    assert "Cobros" in close.reply


def test_adri_does_not_treat_ya_pague_as_payment() -> None:
    shop = make_shop()
    result = shop.handle_turn(shop.store.tenant_id, "59170001115", "Ya pagué.")
    assert result.employee == "Adri"
    assert "No encontré esa prenda" not in result.reply
    lowered = result.reply.lower()
    assert "no" in lowered and ("pago" in lowered or "cobros" in lowered or "sistema" in lowered)


def test_missing_promo_is_not_invented() -> None:
    shop = make_shop()
    result = shop.handle_turn(shop.store.tenant_id, "59170001116", "¿Tienen 20% de descuento?")
    lowered = result.reply.lower()
    assert "No encontré esa prenda" not in result.reply
    assert "invent" in lowered or "no hay" in lowered
    assert "20%" not in result.reply


def test_support_plus_new_sale_are_distinct() -> None:
    shop = make_shop()
    result = shop.handle_turn(
        shop.store.tenant_id,
        "59170001117",
        "Mi pedido llegó ayer y necesito otro igual.",
    )
    assert result.employee == "Postventa"
    lowered = result.reply.lower()
    assert "pedido" in lowered or "postventa" in lowered or "reclamo" in lowered
    assert "prenda" in lowered or "adri" in lowered or "catálogo" in lowered or "catalogo" in lowered
    assert "Pedido creado" not in result.reply


def test_semantic_seda_search_returns_real_sku() -> None:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_pilot_catalog(store)
    hits = search_catalog(store, PILOT_TENANT_ID, "Busco una blusa de seda elegante.")
    assert hits
    known = {record.product_sku for record in store.variants.values()}
    assert hits[0].product_sku in known
    shop = make_shop()
    result = shop.handle_turn(
        shop.store.tenant_id, "59170001118", "Busco una blusa de seda elegante."
    )
    codes = {str(hit.codigo) for hit in hits if hit.codigo}
    assert "seda" in result.reply.lower() or "blusa" in result.reply.lower()


def test_sales_payment_tool_never_runs_handler() -> None:
    shop = make_shop()
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    try:
        shop.tools.execute(adri, "payment.create_qr", {"order_id": "x"})
        raise AssertionError("handler must not run")
    except PermissionDenied:
        pass
    with pytest.raises(PolicyDenied):
        shop.tools.execute(adri, "cart.add", {"sku": "x"})

    before = shop.tools.handler_calls
    with pytest.raises(PermissionDenied):
        shop.tools.execute(adri, "catalog.upsert", {"variant_sku": "x", "name": "no"})
    assert shop.tools.handler_calls == before


def test_typo_hol_is_greeting_not_missing_product() -> None:
    shop = make_shop()
    result = shop.handle_turn(shop.store.tenant_id, "59170001119", "hol")
    assert result.employee == "Adri"
    assert "No encontré esa prenda" not in result.reply
    assert "hola" in result.reply.lower() or "prenda" in result.reply.lower()


def test_quiero_blusa_with_code_creates_order() -> None:
    shop = make_shop()
    result = shop.handle_turn(shop.store.tenant_id, "59170001120", "quiero la blusa pago1")
    assert "Te paso con Cobros para el QR" in result.reply
    assert "Cobros" in result.reply
    assert "pago1" in result.reply.lower()


def test_quiero_pago1_on_closet_overlay() -> None:
    from factory_os.agents.turn import ShopRuntime
    from factory_os.domain.seed import closet_seed_path
    from factory_os.tools.registry import FakePaymentProvider

    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(closet_seed_path(), store)
    for extra in extra_seed_paths("closet"):
        load_catalog_json(extra, store)
    shop = ShopRuntime(store, FakePaymentProvider())
    result = shop.handle_turn(shop.store.tenant_id, "59170001121", "quiero la blusa pago1")
    assert "1.00" in result.reply
    assert "Te paso con Cobros para el QR" in result.reply
    assert "pago1" in result.reply.lower()
    assert "Para pagar" in result.reply or "QR" in result.reply
    assert result.role in {"sales", "collections"}


def test_live_code_pago1_without_quiero_searches() -> None:
    """Customer names live code without buy verb — show the item, don't ask for the code again."""
    from factory_os.agents.turn import ShopRuntime
    from factory_os.domain.seed import closet_seed_path, extra_seed_paths, load_catalog_json
    from factory_os.domain.store import MemoryCommerceStore
    from factory_os.tools.registry import FakePaymentProvider

    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(closet_seed_path(), store)
    for extra in extra_seed_paths("closet"):
        load_catalog_json(extra, store)
    shop = ShopRuntime(store, FakePaymentProvider())
    shop.handle_turn(shop.store.tenant_id, "59170001121d", "Buenos dias, estoy bsucnado una blusa")
    result = shop.handle_turn(
        shop.store.tenant_id,
        "59170001121d",
        "ya recorde el coddigo del live es prueba1 o pago1",
    )
    lowered = result.reply.lower()
    assert "pago1" in lowered
    assert "1.00" in result.reply or "1 bob" in lowered
    assert "pásame el código del live" not in lowered
    assert "pasame el codigo del live" not in normalize(result.reply)


def test_quiero_pago_spaced_closes_order() -> None:
    from factory_os.agents.turn import ShopRuntime
    from factory_os.domain.seed import closet_seed_path
    from factory_os.tools.registry import FakePaymentProvider

    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(closet_seed_path(), store)
    for extra in extra_seed_paths("closet"):
        load_catalog_json(extra, store)
    shop = ShopRuntime(store, FakePaymentProvider())
    result = shop.handle_turn(shop.store.tenant_id, "59170001121c", "quiero la blusa pago 1")
    assert "Te paso con Cobros para el QR" in result.reply
    assert "pago1" in result.reply.lower()
    assert "Para pagar" in result.reply or "QR" in result.reply


def test_quiero_comprar_esa_closes_and_issues_qr() -> None:
    """LLM create_order + shown variant closes — no magic-word dictionary required."""
    import factory_os.agents.graph as graph_mod
    from factory_os.agents.turn import ShopRuntime
    from factory_os.domain.catalog import search_catalog
    from factory_os.domain.seed import closet_seed_path, extra_seed_paths, load_catalog_json
    from factory_os.domain.store import MemoryCommerceStore
    from factory_os.harness.model_gateway import ActionProposal, DraftResult
    from factory_os.tools.registry import FakePaymentProvider

    graph_mod._GRAPH = None
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(closet_seed_path(), store)
    for extra in extra_seed_paths("closet"):
        load_catalog_json(extra, store)

    class CloseGateway:
        """Simulates live LLM that understands natural acceptance."""

        is_deterministic = True

        def propose(self, **_kwargs):
            self.last_event = {"provider": "gemini", "parsed": True, "used_fallback": False}
            return ActionProposal(
                NextAction.CREATE_ORDER,
                "sales_closing",
                provider="gemini",
            )

        def propose_who(self, **_kwargs):
            return None

        def draft(self, *, fallback: str, **_kwargs):
            return DraftResult(text=fallback, provider="script")

    shop = ShopRuntime(store, FakePaymentProvider())
    shop.gateway = CloseGateway()

    wa = "59170001950"
    hits = search_catalog(store, PILOT_TENANT_ID, "pago1")
    assert hits
    customer = store.get_or_create_customer(PILOT_TENANT_ID, wa)
    conv = store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    hit = hits[0]
    conv.state.considered_variant_sku = hit.variant_sku
    conv.state.last_hits = [
        {
            "variant_sku": hit.variant_sku,
            "codigo": hit.codigo,
            "name": hit.name,
            "price": str(hit.price),
            "currency": hit.currency,
            "stock": hit.stock,
        }
    ]
    store.save_conversation_state(conv)

    result = shop.handle_turn(PILOT_TENANT_ID, wa, "dale esa me sirve pasame el qr")
    conv = store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    assert conv.state.order_id is not None
    reserved = shop.store.get_order(PILOT_TENANT_ID, conv.state.order_id)
    assert reserved is not None and reserved.status == "reserved"
    assert conv.state.provider_ref is not None
    assert result.role == "collections"
    assert "Te paso con Cobros para el QR" in result.reply
    assert "Para pagar" in result.reply or "QR" in result.reply


def test_browse_seda_lists_without_creating_order() -> None:
    shop = make_shop()
    result = shop.handle_turn(shop.store.tenant_id, "59170001123", "busco una blusa de seda")
    assert "Pedido creado" not in result.reply
    assert "seda" in result.reply.lower() or "blusa" in result.reply.lower()
    assert shop.store.list_orders(shop.store.tenant_id) == []


def test_llm_create_order_without_shown_item_is_not_executed() -> None:
    class CloseGateway:
        def propose(self, **_kwargs):
            return ActionProposal(NextAction.CREATE_ORDER, "sales_closing", provider="script")

        def draft(self, *, fallback: str, **_kwargs):
            return DraftResult(text=fallback, provider="script")

    shop = make_shop()
    shop.gateway = CloseGateway()
    # No considered variant yet → CREATE_ORDER cannot bind → search instead.
    result = shop.handle_turn(shop.store.tenant_id, "59170001124", "quiero una blusa de seda")
    assert "Pedido creado" not in result.reply
    assert "seda" in result.reply.lower() or "blusa" in result.reply.lower()
    assert shop.store.list_orders(shop.store.tenant_id) == []

    # Objection is an LLM decision, not a keyword block on close.
    class ObjectionGateway:
        def propose(self, **_kwargs):
            return ActionProposal(NextAction.HANDLE_OBJECTION, "objection_handling", provider="script")

        def draft(self, *, fallback: str, **_kwargs):
            return DraftResult(text=fallback, provider="script")

    shop.handle_turn(shop.store.tenant_id, "59170001125", "quiero una blusa de seda")
    shop.gateway = ObjectionGateway()
    objection = shop.handle_turn(shop.store.tenant_id, "59170001125", "Está muy caro.")
    assert "Pedido creado" not in objection.reply
    assert shop.store.list_orders(shop.store.tenant_id) == []


def test_llm_wrong_skill_on_named_code_still_creates_order() -> None:
    """Gemini often returns create_order + customer_assistance; BBE must not block cart.add."""

    class WrongSkillGateway:
        def propose(self, **_kwargs):
            return ActionProposal(NextAction.CREATE_ORDER, "customer_assistance", provider="script")

        def draft(self, *, fallback: str, **_kwargs):
            return DraftResult(text=fallback, provider="script")

    shop = make_shop()
    shop.gateway = WrongSkillGateway()
    result = shop.handle_turn(shop.store.tenant_id, "59170001127", "quiero la blusa pago1")
    assert "Te paso con Cobros para el QR" in result.reply
    assert "bloqueó" not in result.reply.lower()
    assert "Cobros" in result.reply


def test_llm_wrong_skill_on_confirm_still_creates_order() -> None:
    class WrongSkillGateway:
        def propose(self, **_kwargs):
            return ActionProposal(NextAction.CREATE_ORDER, "customer_assistance", provider="script")

        def draft(self, *, fallback: str, **_kwargs):
            return DraftResult(text=fallback, provider="script")

    shop = make_shop()
    shop.handle_turn(shop.store.tenant_id, "59170001128", "quiero una blusa de seda")
    shop.gateway = WrongSkillGateway()
    close = shop.handle_turn(shop.store.tenant_id, "59170001128", "confirmo")
    assert "Te paso con Cobros para el QR" in close.reply
    assert "bloqueó" not in close.reply.lower()


def test_shown_item_then_confirm_creates_order() -> None:
    shop = make_shop()
    shop.handle_turn(shop.store.tenant_id, "59170001126", "quiero una blusa de seda")
    close = shop.handle_turn(shop.store.tenant_id, "59170001126", "confirmo")
    assert "Te paso con Cobros para el QR" in close.reply
    orders = shop.store.list_orders(shop.store.tenant_id)
    assert len(orders) == 1
    assert orders[0].status == "reserved"
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert conv.state.provider_ref


def test_invented_business_claims_are_dropped_from_draft() -> None:
    class LyingGateway:
        def propose(self, **_kwargs):
            return None

        def draft(self, *, fallback: str, **_kwargs):
            return DraftResult(
                text="Hay 20% de descuento, ya está pago y quedan 999 unidades.",
                provider="script",
            )

    shop = make_shop()
    shop.gateway = LyingGateway()
    result = shop.handle_turn(shop.store.tenant_id, "59170001122", "hola")
    lowered = result.reply.lower()
    assert "20%" not in result.reply
    assert "ya está pago" not in lowered and "ya esta pago" not in lowered
    assert "999" not in result.reply
    assert "prenda" in lowered or "hola" in lowered


def test_budget_question_is_catalog_search() -> None:
    action, skill = next_best_action(WorkingState(), "tiene alguna cueste 1 bs?")
    assert action is NextAction.SEARCH_CATALOG
    assert skill == "product_recommendation"


def test_budget_question_searches_even_if_llm_calls_it_objection() -> None:
    class ObjGateway:
        is_deterministic = True

        def propose(self, **_kwargs):
            return ActionProposal(
                NextAction.HANDLE_OBJECTION,
                "customer_assistance",
                arguments={"tool": "handle_objection"},
                provider="script",
            )

        def draft(self, *, fallback: str, **_kwargs):
            return DraftResult(text=fallback, provider="script")

    shop = make_shop()
    shop.handle_turn(shop.store.tenant_id, "59170001130", "quiero una blusa de seda")
    shop.gateway = ObjGateway()
    result = shop.handle_turn(shop.store.tenant_id, "59170001130", "tiene alguna cueste 150 bs?")
    assert "Pedido creado" not in result.reply
    assert any(token in result.reply for token in ("150", "BOB", "blusa", "seda")) or "bs" in result.reply.lower()
    assert "Pedido creado" not in result.reply


def test_closet_budget_search_hides_test_only_pago_items() -> None:
    """T13: pago1–pago4 are test_only — budget search must not surface them; exact code still works."""
    from factory_os.agents.turn import ShopRuntime
    from factory_os.domain.catalog import search_catalog
    from factory_os.domain.seed import closet_seed_path
    from factory_os.tools.registry import FakePaymentProvider

    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(closet_seed_path(), store)
    for extra in extra_seed_paths("closet"):
        load_catalog_json(extra, store)
    shop = ShopRuntime(store, FakePaymentProvider())
    browse = shop.handle_turn(shop.store.tenant_id, "59170001131", "estoy buscando blusas")
    assert "Pedido creado" not in browse.reply
    lowered = browse.reply.lower()
    assert all(code not in lowered for code in ("pago1", "pago2", "pago3", "pago4"))
    assert "prueba pago" not in lowered

    budget_hits = search_catalog(store, PILOT_TENANT_ID, "blusas", budget_max=__import__("decimal").Decimal("1"))
    assert all(hit.codigo not in {"pago1", "pago2", "pago3", "pago4"} for hit in budget_hits)

    exact = shop.handle_turn(shop.store.tenant_id, "59170001131b", "quiero la blusa pago1")
    assert "Te paso con Cobros para el QR" in exact.reply
    assert "pago1" in exact.reply.lower()


def test_llm_catalog_search_tool_runs_read() -> None:
    class SearchGateway:
        def propose(self, **_kwargs):
            return ActionProposal(
                NextAction.ANSWER,
                "customer_assistance",
                arguments={"tool": "catalog.search", "query": "blusa de seda"},
                provider="script",
            )

        def draft(self, *, fallback: str, **_kwargs):
            return DraftResult(text=fallback, provider="script")

    shop = make_shop()
    shop.gateway = SearchGateway()
    result = shop.handle_turn(shop.store.tenant_id, "59170001132", "mostrame blusas de seda")
    assert "seda" in result.reply.lower() or "blusa" in result.reply.lower()
    assert "BOB" in result.reply or "bs" in result.reply.lower()


def test_llm_payment_tool_is_not_executed() -> None:
    class PayGateway:
        def propose(self, **_kwargs):
            return ActionProposal(
                NextAction.CREATE_ORDER,
                "sales_closing",
                arguments={"tool": "payment.create_qr"},
                provider="script",
            )

        def draft(self, *, fallback: str, **_kwargs):
            return DraftResult(text=fallback, provider="script")

    shop = make_shop()
    shop.gateway = PayGateway()
    before = shop.tools.handler_calls
    result = shop.handle_turn(shop.store.tenant_id, "59170001133", "pasame el qr")
    lowered = result.reply.lower()
    assert "Pedido creado" not in result.reply
    assert "qr" in lowered or "cobros" in lowered
    assert shop.tools.handler_calls == before


def test_llm_discovery_does_not_block_named_garment_search() -> None:
    class DiscoverGateway:
        def propose(self, **_kwargs):
            return ActionProposal(NextAction.ASK_DISCOVERY_QUESTION, "sales_discovery", provider="script")

        def draft(self, *, fallback: str, **_kwargs):
            return DraftResult(text=fallback, provider="script")

    shop = make_shop()
    shop.gateway = DiscoverGateway()
    # Named garment + fabric is not thin: coerce discovery → search.
    result = shop.handle_turn(shop.store.tenant_id, "59170001134", "estoy buscando blusa de seda")
    assert "presupuesto" not in result.reply.lower()
    assert "blusa" in result.reply.lower() or "crep" in result.reply.lower()
    assert "Pedido creado" not in result.reply


def test_category_only_asks_discovery_before_list() -> None:
    shop = make_shop()
    first = shop.handle_turn(shop.store.tenant_id, "59170001135", "estoy buscando blusas")
    assert "presupuesto" in first.reply.lower() or "talla" in first.reply.lower()
    assert "encontré estas opciones" not in first.reply.lower()
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert conv.state.discovery_asked
    assert conv.state.stage is ConversationStage.DISCOVERY
    second = shop.handle_turn(shop.store.tenant_id, "59170001135", "talla M para oficina")
    assert "encontré" in second.reply.lower() or "opción" in second.reply.lower() or "código" in second.reply.lower()
