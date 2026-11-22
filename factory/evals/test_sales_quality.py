"""Fase 0 — deterministic sales quality corpus (MODEL_PROVIDER=fake)."""

from __future__ import annotations

import os

import pytest

from evals.sales_quality.rules import load_corpus
from evals.sales_quality.runner import run_case, run_corpus
from factory_os.domain.postgres import apply_migrations, connect
from factory_os.harness.agent_trace import AgentTraceLog, postgres_trace_sink


def test_corpus_has_twenty_five_cases() -> None:
    corpus = load_corpus()
    assert len(corpus["cases"]) == 25
    failures = {c["failure"] for c in corpus["cases"]}
    assert failures >= {"F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"}


def test_sales_quality_corpus_baseline() -> None:
    results, summary = run_corpus()
    assert summary["cases"] == 25
    hard_ids = {
        "sq_05_f4_exact_code_closes",
        "sq_10_f6_no_archivo_jargon",
        "sq_12_f7_hide_pago_in_browse",
        "sq_13_f7_exact_pago_ok",
        "sq_20_f4_confirm_after_show",
    }
    by_id = {r.case_id: r for r in results}
    for case_id in hard_ids:
        assert by_id[case_id].ok, (case_id, by_id[case_id].failed_names, by_id[case_id].last_reply)
    assert all(r.last_reply.strip() for r in results)
    # Gate: must not regress below recorded baseline (evals/sales_quality/baseline.json).
    assert summary["pass_rate"] >= 0.88, summary
    assert summary["failed"] == 0, summary["failed_ids"]


@pytest.mark.parametrize("case", load_corpus()["cases"], ids=lambda c: c["id"])
def test_each_sales_quality_case_runs(case: dict) -> None:
    from evals.sales_quality.runner import make_eval_shop

    shop = make_eval_shop(closet=True)
    result = run_case(shop, case)
    assert result.last_reply.strip()
    for check in result.checks:
        if check.name in {"no_internal_jargon", "address_tu"} and check.name in (
            case.get("expect") or {}
        ).get("checks", []):
            assert check.ok, (case["id"], check.name, check.detail, result.last_reply)


def test_agent_trace_persists_when_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    url = os.environ.get("FACTORY_OS_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    try:
        apply_migrations(url)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"postgres not reachable: {exc}")
    from uuid import uuid4

    cid = str(uuid4())
    trace = AgentTraceLog(sink=postgres_trace_sink(url))
    trace.begin_turn(conversation_id=cid, employee="Adri", role="sales")
    trace.record("sales_decision", parsed_action="answer", payload={"fase0": True})
    trace.end_turn()
    with connect(url) as conn:
        row = conn.execute(
            "SELECT count(*) AS c FROM agent_trace_events WHERE conversation_id = %s",
            (cid,),
        ).fetchone()
    assert int(row["c"]) >= 1
