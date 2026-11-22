"""SalesDecision contract (ADR-003) — validation and preference provenance."""

from __future__ import annotations

from decimal import Decimal

from uuid import uuid4

from factory_os.agents.sales import _facts
from factory_os.domain.models import Conversation, NextAction, WorkingState
from factory_os.domain.response_goals import (
    RESPONSE_GOAL_CODES,
    normalize_response_goal,
    phrase_for_response_goal,
)
from factory_os.domain.sales_decision import (
    PreferencePatch,
    SalesDecision,
    apply_preference_patch,
    parse_sales_decision,
    validate_sales_decision,
)
from factory_os.harness.model_gateway import parse_proposal
from tests.conftest import make_shop


def test_parse_sales_decision_full_shape() -> None:
    decision = parse_sales_decision(
        {
            "action": "search_catalog",
            "skill": "product_recommendation",
            "understanding": "busca blusas baratas",
            "preference_patch": {"budget_max": "80", "color": "negro", "durable": True},
            "tool_call": {"name": "catalog.search", "arguments": {"query": "blusas"}},
            "response_goal": "show_options",
        },
        provider="gemini",
    )
    assert decision is not None
    assert decision.response_goal == "show_options"
    assert decision.action is NextAction.SEARCH_CATALOG
    assert decision.preference_patch.budget_max == Decimal("80")
    assert decision.preference_patch.durable is True
    assert validate_sales_decision(decision) == []


def test_rejects_payment_tool_for_adri() -> None:
    decision = parse_sales_decision(
        {
            "action": "answer",
            "tool_call": {"name": "payment.create_qr", "arguments": {}},
        },
        provider="gemini",
    )
    assert decision is not None
    assert "tool not allowed" in validate_sales_decision(decision)[0]
    # parse_proposal strips illegal tools
    proposal = parse_proposal(
        '{"action":"answer","tool_call":{"name":"payment.create_qr","arguments":{}}}',
        "gemini",
    )
    assert proposal is not None
    assert proposal.decision is not None
    assert proposal.decision.tool_call is None


def test_durable_preferences_persist_inferred_do_not() -> None:
    state = WorkingState()
    durable = PreferencePatch(budget_max=Decimal("50"), size="M", durable=True)
    turn = apply_preference_patch(state, durable)
    assert turn == {}
    assert state.budget_max == Decimal("50")
    assert state.size == "M"
    assert state.preference_provenance["budget_max"] == "customer_explicit"

    inferred = PreferencePatch(color="rojo", durable=False)
    turn2 = apply_preference_patch(state, inferred)
    assert turn2 == {"color": "rojo"}
    assert state.color is None
    assert "color" not in state.preference_provenance


def test_scripted_sales_decision_applies_budget_patch() -> None:
    shop = make_shop()

    class Desk:
        last_event = {"provider": "gemini", "parsed": True, "model": "x", "used_fallback": False}

        def propose(self, **_kwargs):
            return parse_proposal(
                '{"action":"search_catalog","skill":"product_recommendation",'
                '"preference_patch":{"budget_max":"100","durable":true},'
                '"tool_call":{"name":"catalog.search","arguments":{"query":"blusas"}},'
                '"understanding":"presupuesto 100","response_goal":"show_options"}',
                "gemini",
            )

        def draft(self, **kwargs):
            from factory_os.harness.model_gateway import DraftResult

            return DraftResult(text=kwargs["fallback"], provider="script", used_fallback=True)

    shop.gateway = Desk()  # type: ignore[assignment]
    result = shop.handle_turn(shop.store.tenant_id, "59191000001", "blusas hasta 100 bob")
    assert result.employee == "Adri"
    conv = shop.store.list_conversations(shop.store.tenant_id)[0]
    assert conv.state.budget_max == Decimal("100")
    assert conv.state.preference_provenance.get("budget_max") == "customer_explicit"


def test_sales_decision_roundtrip_legacy_tool_shape() -> None:
    proposal = parse_proposal(
        '{"action":"search_catalog","tool":"catalog.search","arguments":{"query":"vestido"}}',
        "gemini",
    )
    assert proposal is not None
    assert proposal.decision is not None
    assert proposal.arguments["tool"] == "catalog.search"
    assert proposal.arguments["query"] == "vestido"


def test_normalize_response_goal_keeps_code_and_drops_free_text() -> None:
    assert normalize_response_goal("recommend_ask_fit") == "recommend_ask_fit"
    assert "recommend_ask_fit" in RESPONSE_GOAL_CODES
    assert normalize_response_goal("preguntar talla y que le late") == ""
    phrase = phrase_for_response_goal("recommend_ask_fit")
    assert phrase
    assert "le late" not in phrase.lower()
    for code in RESPONSE_GOAL_CODES:
        rendered = phrase_for_response_goal(code)
        assert rendered
        assert "le late" not in rendered.lower()
    assert phrase_for_response_goal("preguntar talla y que le late") == ""


def test_parse_drops_legacy_free_text_response_goal() -> None:
    decision = parse_sales_decision(
        {"action": "answer", "response_goal": "preguntar talla y que le late"},
        provider="gemini",
    )
    assert decision is not None
    assert decision.response_goal == ""


def test_sales_facts_translate_response_goal_before_draft() -> None:
    conversation = Conversation(id=uuid4(), tenant_id=uuid4(), customer_id=uuid4())
    facts = _facts(conversation, {"response_goal": "greet"})
    assert facts["response_goal"] == phrase_for_response_goal("greet")
    assert "le late" not in facts["response_goal"].lower()
    assert facts["response_goal"] != "greet"
    dropped = _facts(conversation, {"response_goal": "preguntar talla y que le late"})
    assert "response_goal" not in dropped
