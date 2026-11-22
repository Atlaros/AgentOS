"""Fase 2 — measure decision/fallback rates over the sales-quality corpus."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from evals.sales_quality.rules import load_corpus, summarize
from evals.sales_quality.runner import make_eval_shop, run_case
from factory_os.harness.agent_trace import AgentTraceLog


def _baseline_path() -> Path:
    return Path(__file__).resolve().parent / "baseline.json"


def _fase2_path() -> Path:
    return Path(__file__).resolve().parent / "fase2.json"


def load_baseline() -> dict[str, Any]:
    return json.loads(_baseline_path().read_text(encoding="utf-8"))


def run_corpus_traced(*, closet: bool = True) -> tuple[list, dict[str, Any], dict[str, Any]]:
    """Run corpus with AgentTraceLog; return results, quality summary, fallback metrics."""
    corpus = load_corpus()
    results = []
    sources: Counter[str] = Counter()
    propose_fallback = 0
    draft_fallback = 0
    tool_reads = 0
    playbook_turns = 0
    decision_turns = 0
    ops_seen: Counter[str] = Counter()

    for case in corpus["cases"]:
        shop = make_eval_shop(closet=closet)
        trace = AgentTraceLog()
        shop.trace = trace
        if getattr(shop.gateway, "trace_log", None) is not None:
            shop.gateway.trace_log = trace  # type: ignore[attr-defined]
        else:
            setattr(shop.gateway, "trace_log", trace)
        result = run_case(shop, case)
        results.append(result)

        for event in trace.events:
            ops_seen[event.operation] += 1
            if event.operation == "sales_decision":
                decision_turns += 1
                sources[str(event.payload.get("decision_source") or "unknown")] += 1
                if event.payload.get("playbook_hits"):
                    playbook_turns += 1
            elif event.operation == "propose" and event.used_fallback:
                propose_fallback += 1
            elif event.operation == "draft" and event.used_fallback:
                draft_fallback += 1
            elif event.operation == "tool_read":
                tool_reads += 1

    quality = summarize(results)
    metrics = {
        "decision_turns": decision_turns,
        "decision_source": dict(sources),
        "propose_used_fallback_events": propose_fallback,
        "draft_used_fallback_events": draft_fallback,
        "tool_read_events": tool_reads,
        "turns_with_playbook_hits": playbook_turns,
        "operations": dict(ops_seen),
        "fallback_decision_rate": round(
            (sources.get("nba_fallback", 0) + sources.get("heuristic", 0)) / decision_turns, 4
        )
        if decision_turns
        else 0.0,
        "sales_decision_rate": round(
            (sources.get("sales_decision", 0) + sources.get("llm_propose", 0)) / decision_turns, 4
        )
        if decision_turns
        else 0.0,
    }
    return results, quality, metrics


def compare_to_baseline(quality: dict[str, Any], baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    base = baseline or load_baseline()
    criteria: dict[str, Any] = {}
    for name, row in (quality.get("criteria") or {}).items():
        prev = (base.get("criteria") or {}).get(name) or {}
        criteria[name] = {
            "rate": row.get("rate"),
            "baseline_rate": prev.get("rate"),
            "delta": round(float(row.get("rate") or 0) - float(prev.get("rate") or 0), 4),
            "ok": float(row.get("rate") or 0) >= float(prev.get("rate") or 0),
        }
    return {
        "pass_rate": quality.get("pass_rate"),
        "baseline_pass_rate": base.get("pass_rate"),
        "pass_rate_ok": float(quality.get("pass_rate") or 0) >= float(base.get("pass_rate") or 0),
        "failed": quality.get("failed"),
        "criteria": criteria,
        "no_regression": all(item["ok"] for item in criteria.values())
        and float(quality.get("pass_rate") or 0) >= float(base.get("pass_rate") or 0),
    }


def build_fase2_report(*, closet: bool = True) -> dict[str, Any]:
    results, quality, metrics = run_corpus_traced(closet=closet)
    baseline = load_baseline()
    comparison = compare_to_baseline(quality, baseline)
    return {
        "measured_at": "2026-09-22",
        "phase": "fase2",
        "model_provider": "fake",
        "catalog": "closet+pay_test",
        "note": (
            "Re-measure after TK4 playbook index. FakeGateway drafts always use_fallback=true "
            "(deterministic reply path); decision_source shows seller authority."
        ),
        "quality": quality,
        "fallback": metrics,
        "vs_baseline": comparison,
        "failed_ids": [r.case_id for r in results if not r.ok],
    }


def write_fase2_report(path: Path | None = None) -> dict[str, Any]:
    report = build_fase2_report()
    out = path or _fase2_path()
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
