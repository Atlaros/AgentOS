"""Fase 2 — fallback metrics and no-regression vs baseline."""

from __future__ import annotations

from evals.sales_quality.measure import build_fase2_report, compare_to_baseline, run_corpus_traced
from evals.sales_quality.rules import load_corpus
from evals.sales_quality.runner import make_eval_shop, run_case
from factory_os.harness.agent_trace import AgentTraceLog
from tests.conftest import make_shop


def test_tool_read_recorded_on_catalog_search() -> None:
    shop = make_shop()
    trace = AgentTraceLog()
    shop.trace = trace
    shop.gateway.trace_log = trace  # type: ignore[attr-defined]
    shop.handle_turn(shop.store.tenant_id, "59191000001", "blusa talla M color blanco")
    ops = [e.operation for e in trace.events]
    assert "sales_decision" in ops
    assert "tool_read" in ops
    assert "who_decision" in ops
    tool = next(e for e in trace.events if e.operation == "tool_read")
    assert tool.payload["tool"] == "catalog.search"
    assert "facts" in tool.payload
    decision = next(e for e in trace.events if e.operation == "sales_decision")
    assert "propose_used_fallback" in decision.payload
    assert "parse_success" in decision.payload


def test_fase2_no_regression_vs_baseline() -> None:
    report = build_fase2_report()
    assert report["quality"]["cases"] == 25
    assert report["quality"]["failed"] == 0
    assert report["vs_baseline"]["no_regression"] is True
    assert report["vs_baseline"]["pass_rate_ok"] is True
    assert report["fallback"]["decision_turns"] >= 25
    # FakeGateway: commercial path is sales_decision; named-code closes may be heuristic.
    sources = report["fallback"]["decision_source"]
    assert sources.get("sales_decision", 0) + sources.get("heuristic", 0) == report["fallback"][
        "decision_turns"
    ]
    assert report["fallback"]["tool_read_events"] >= 1
    assert report["fallback"]["turns_with_playbook_hits"] >= 1


def test_compare_detects_regression() -> None:
    _, quality, _ = run_corpus_traced()
    broken = dict(quality)
    broken["pass_rate"] = 0.5
    broken["criteria"] = {
        name: {**row, "rate": 0.0} for name, row in (quality.get("criteria") or {}).items()
    }
    cmp = compare_to_baseline(broken)
    assert cmp["no_regression"] is False
    assert cmp["pass_rate_ok"] is False


def test_append_golden_dry_run_shape() -> None:
    # Smoke: corpus still loads after Fase 2 tooling.
    assert len(load_corpus()["cases"]) == 25
    shop = make_eval_shop(closet=True)
    case = load_corpus()["cases"][0]
    result = run_case(shop, case)
    assert result.last_reply
