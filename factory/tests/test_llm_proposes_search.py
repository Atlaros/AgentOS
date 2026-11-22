"""ODD v2-llm-proposes-catalog-search: LLM proposes search; runtime does not keyword-fire."""

from __future__ import annotations

from factory_os.agents.turn import ShopRuntime
from factory_os.domain.catalog import format_product_rag, search_catalog
from factory_os.domain.models import (
    NextAction,
    PILOT_TENANT_ID,
)
from factory_os.domain.seed import closet_seed_path, extra_seed_paths, load_catalog_json, normalize
from factory_os.domain.store import MemoryCommerceStore
from factory_os.harness.model_gateway import ActionProposal, DraftResult
from factory_os.tools.registry import FakePaymentProvider
from tests.conftest import make_shop


def _closet_shop() -> ShopRuntime:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(closet_seed_path(), store)
    for extra in extra_seed_paths("closet"):
        load_catalog_json(extra, store)
    return ShopRuntime(store, FakePaymentProvider())


def test_format_product_rag_omits_price_and_stock() -> None:
    shop = make_shop()
    hits = search_catalog(shop.store, PILOT_TENANT_ID, "blusa", limit=3)
    blob = format_product_rag(hits)
    assert "product_rag:" in blob
    assert "precio" not in blob.lower()
    assert "price=" not in blob.lower()
    assert "stock=" not in blob.lower()
    assert "DATABASE_URL" not in blob
    assert "costo" not in blob.lower()


def test_live_code_pago1_fake_searches_not_tiktok_faq() -> None:
    """Incident golden: named live code → catalog hit, never 'pásame el código'."""
    shop = _closet_shop()
    shop.handle_turn(shop.store.tenant_id, "59170002201", "Buenos dias, estoy bsucnado una blusa")
    result = shop.handle_turn(
        shop.store.tenant_id,
        "59170002201",
        "ya recorde el coddigo del live es prueba1 o pago1",
    )
    lowered = result.reply.lower()
    assert "pago1" in lowered
    assert "pásame el código del live" not in lowered
    assert "pasame el codigo del live" not in normalize(result.reply)
    customer = shop.store.get_or_create_customer(shop.store.tenant_id, "59170002201")
    conv = shop.store.get_or_create_conversation(shop.store.tenant_id, customer)
    assert conv.state.last_action == NextAction.SEARCH_CATALOG.value


def test_llm_answer_without_tool_does_not_force_search_or_faq() -> None:
    """Authority: live LLM proposes ANSWER → runtime must not keyword-force SEARCH/FAQ."""
    from factory_os.domain.sales_decision import PreferencePatch, SalesDecision

    class LiveAnswerGateway:
        is_deterministic = False
        last_event: dict = {}

        def propose(self, *, role, context, text, state):
            _ = role, context, text, state
            self.last_event = {
                "op": "propose",
                "provider": "gemini",
                "parsed": True,
                "used_fallback": False,
            }
            decision = SalesDecision(
                action=NextAction.ANSWER,
                skill="customer_assistance",
                understanding="cliente habla del live",
                preference_patch=PreferencePatch(),
                tool_call=None,
                response_goal="ask_detail",
                provider="gemini",
            )
            return ActionProposal.from_sales_decision(decision)

        def propose_who(self, *, context, text, state):
            _ = context, text, state
            self.last_event = {"op": "propose_who", "provider": "gemini", "parsed": True}
            return "sales"

        def draft(self, *, role, context, facts, fallback):
            _ = role, context, facts
            return DraftResult(text=fallback, provider="gemini", used_fallback=True)

    shop = _closet_shop()
    shop.gateway = LiveAnswerGateway()
    text = "ya recorde el coddigo del live es prueba1 o pago1"
    result = shop.handle_turn(shop.store.tenant_id, "59170002202", text)
    lowered = result.reply.lower()
    assert "pásame el código del live" not in lowered
    assert "pasame el codigo del live" not in normalize(result.reply)
    customer = shop.store.get_or_create_customer(shop.store.tenant_id, "59170002202")
    conv = shop.store.get_or_create_conversation(shop.store.tenant_id, customer)
    # Must not have been forced to SEARCH by product_code tokens.
    assert conv.state.last_action == NextAction.ANSWER.value


def test_llm_proposes_catalog_search_pago1_grounds() -> None:
    """Positive: LLM proposes catalog.search query=pago1 → hits with real price."""
    from factory_os.domain.sales_decision import PreferencePatch, SalesDecision

    class LiveSearchGateway:
        is_deterministic = False
        last_event: dict = {}

        def propose(self, *, role, context, text, state):
            _ = role, text, state
            self.last_event = {
                "op": "propose",
                "provider": "gemini",
                "parsed": True,
                "used_fallback": False,
            }
            decision = SalesDecision(
                action=NextAction.SEARCH_CATALOG,
                skill="product_recommendation",
                understanding="cliente nombró pago1",
                preference_patch=PreferencePatch(),
                tool_call={"name": "catalog.search", "arguments": {"query": "pago1"}},
                response_goal="show_options",
                provider="gemini",
            )
            return ActionProposal.from_sales_decision(decision)

        def propose_who(self, *, context, text, state):
            _ = context, text, state
            self.last_event = {"op": "propose_who", "provider": "gemini", "parsed": True}
            return "sales"

        def draft(self, *, role, context, facts, fallback):
            _ = role, context
            hits = facts.get("hits") or []
            if hits:
                hit = hits[0]
                return DraftResult(
                    text=(
                        f"La {hit.get('name')} está a {hit.get('price')} "
                        f"{hit.get('currency')} (código {hit.get('codigo')}). ¿Te late?"
                    ),
                    provider="gemini",
                    used_fallback=False,
                )
            return DraftResult(text=fallback, provider="gemini", used_fallback=True)

    shop = _closet_shop()
    shop.gateway = LiveSearchGateway()
    result = shop.handle_turn(
        shop.store.tenant_id,
        "59170002203",
        "ya recorde el coddigo del live es prueba1 o pago1",
    )
    assert "pago1" in result.reply.lower()
    assert "1.00" in result.reply or "1 bob" in result.reply.lower()
    customer = shop.store.get_or_create_customer(shop.store.tenant_id, "59170002203")
    conv = shop.store.get_or_create_conversation(shop.store.tenant_id, customer)
    assert conv.state.last_action == NextAction.SEARCH_CATALOG.value
    assert any(str(h.get("codigo")) == "pago1" for h in conv.state.last_hits)
