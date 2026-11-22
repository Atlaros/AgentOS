"""Observability for agent harness — no commercial behavior changes."""

from __future__ import annotations

from factory_os.domain.models import NextAction, WorkingState
from factory_os.harness.agent_trace import AgentTraceLog, snapshot_working_state
from factory_os.harness.model_gateway import ActionProposal, DraftResult, FailoverGateway, HttpProvider
from tests.conftest import make_shop


def test_snapshot_working_state_fields() -> None:
    state = WorkingState()
    snap = snapshot_working_state(state)
    assert set(snap) >= {
        "stage",
        "last_action",
        "last_skill",
        "next_best_action",
        "customer_need",
        "discovery_asked",
        "considered_variant_sku",
        "last_hits",
        "cart",
        "order_id",
    }


def test_propose_and_draft_are_recorded() -> None:
    trace = AgentTraceLog()
    shop = make_shop()
    shop.trace = trace
    shop.gateway.trace_log = trace  # type: ignore[attr-defined]

    result = shop.handle_turn(shop.store.tenant_id, "59190000001", "hola")
    assert result.employee == "Adri"

    ops = [event.operation for event in trace.for_conversation(result.conversation_id)]
    assert "propose" in ops
    assert "draft" in ops
    assert "state_before" in ops
    assert "state_after" in ops
    assert "sales_decision" in ops


def test_decision_source_sales_decision_for_named_code() -> None:
    """FakeGateway proposes CREATE_ORDER via SalesDecision (no live keyword override)."""
    trace = AgentTraceLog()
    shop = make_shop()
    shop.trace = trace
    shop.gateway.trace_log = trace  # type: ignore[attr-defined]

    result = shop.handle_turn(shop.store.tenant_id, "59190000002", "quiero la blusa p001")
    assert "Te paso con Cobros para el QR" in result.reply

    decision = next(
        event
        for event in trace.for_conversation(result.conversation_id)
        if event.operation == "sales_decision"
    )
    assert decision.payload["decision_source"] == "sales_decision"
    assert decision.payload["final_action"] == "create_order"


def test_decision_source_sales_decision_for_blusas() -> None:
    trace = AgentTraceLog()
    shop = make_shop()
    shop.trace = trace
    shop.gateway.trace_log = trace  # type: ignore[attr-defined]

    result = shop.handle_turn(shop.store.tenant_id, "59190000003", "estoy bsucnado blusas")
    assert result.employee == "Adri"

    decision = next(
        event
        for event in trace.for_conversation(result.conversation_id)
        if event.operation == "sales_decision"
    )
    assert decision.payload["decision_source"] == "sales_decision"
    assert decision.payload["final_action"] == "ask_discovery_question"
    assert decision.payload["final_skill"] == "sales_discovery"
    assert decision.payload.get("sales_decision") is not None


def test_decision_source_llm_propose() -> None:
    trace = AgentTraceLog()

    class ScriptGateway:
        trace_log = trace
        last_event: dict = {}

        def propose(self, **_kwargs):
            self.last_event = {
                "op": "propose",
                "provider": "gemini",
                "model": "gemini-test",
                "parsed": True,
                "used_fallback": False,
            }
            return ActionProposal(NextAction.SEARCH_CATALOG, "product_recommendation", provider="gemini")

        def draft(self, *, role, context, facts, fallback):
            _ = role, context, facts
            self.last_event = {
                "op": "draft",
                "provider": "gemini",
                "model": "gemini-test",
                "used_fallback": False,
                "grounding_ok": True,
            }
            trace.record(
                "draft",
                provider="gemini",
                model="gemini-test",
                used_fallback=False,
                payload={
                    "fallback_text": fallback,
                    "facts": facts,
                    "compile_context": context,
                    "raw_draft": fallback,
                    "grounding_ok": True,
                    "final_rendered_reply": fallback,
                },
            )
            return DraftResult(text=fallback, provider="gemini", used_fallback=False)

    shop = make_shop()
    shop.trace = trace
    shop.gateway = ScriptGateway()  # type: ignore[assignment]

    result = shop.handle_turn(shop.store.tenant_id, "59190000004", "estoy bsucnado blusas")
    decision = next(
        event
        for event in trace.for_conversation(result.conversation_id)
        if event.operation == "sales_decision"
    )
    assert decision.payload["decision_source"] == "llm_propose"
    assert decision.payload["propose_parse_success"] is True
    assert decision.provider == "gemini"
    assert decision.model == "gemini-test"


def test_state_before_after_recorded() -> None:
    trace = AgentTraceLog()
    shop = make_shop()
    shop.trace = trace
    shop.gateway.trace_log = trace  # type: ignore[attr-defined]

    first = shop.handle_turn(shop.store.tenant_id, "59190000005", "hola")
    second = shop.handle_turn(shop.store.tenant_id, "59190000005", "estoy bsucnado blusas")
    assert first.conversation_id == second.conversation_id

    events = trace.for_conversation(second.conversation_id)
    befores = [event for event in events if event.operation == "state_before"]
    afters = [event for event in events if event.operation == "state_after"]
    assert len(befores) == 2
    assert len(afters) == 2
    assert afters[-1].payload["state"]["last_action"] == "ask_discovery_question"
    assert afters[-1].payload["state"]["discovery_asked"] is True


def test_failover_gateway_records_provider_and_model() -> None:
    trace = AgentTraceLog()

    def complete(system: str, user: str, timeout: float, temperature: float = 0.2):
        _ = system, user, timeout, temperature
        return '{"action":"search_catalog","skill":"product_recommendation"}', 9

    gateway = FailoverGateway(
        [HttpProvider("gemini", complete, model_id="gemini-test-id")],
        trace_log=trace,
    )
    trace.begin_turn(conversation_id="conv-1", employee="Adri", role="sales")
    proposal = gateway.propose(
        role="sales",
        context="employee=Adri",
        text="estoy bsucnado blusas",
        state=WorkingState(),
    )
    assert proposal is not None
    assert proposal.action is NextAction.SEARCH_CATALOG

    draft = gateway.draft(
        role="sales",
        context="employee=Adri",
        facts={"hits": [{"price": "1.00", "codigo": "p001", "product_sku": "p001"}]},
        fallback="Encontré p001 a 1.00 BOB",
    )
    assert draft.text

    propose_event = next(event for event in trace.events if event.operation == "propose")
    draft_event = next(event for event in trace.events if event.operation == "draft")
    assert propose_event.provider == "gemini"
    assert propose_event.model == "gemini-test-id"
    assert propose_event.prompt
    assert propose_event.raw_response
    assert draft_event.payload["fallback_text"].startswith("Encontré")
    assert "compile_context" in draft_event.payload
    assert "grounding_ok" in draft_event.payload
    assert "final_rendered_reply" in draft_event.payload


def test_existing_sales_behavior_unchanged_with_trace() -> None:
    shop = make_shop()
    browse = shop.handle_turn(shop.store.tenant_id, "59190000006", "quiero una blusa de seda")
    assert "Pedido creado" not in browse.reply
    assert "seda" in browse.reply.lower() or "blusa" in browse.reply.lower()
    close = shop.handle_turn(shop.store.tenant_id, "59190000006", "confirmo")
    assert "Te paso con Cobros para el QR" in close.reply
    assert any(event.operation == "sales_decision" for event in shop.trace.events)
