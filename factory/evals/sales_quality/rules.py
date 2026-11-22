"""Deterministic sales-quality rules over Adri replies (MODEL_PROVIDER=fake)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_OPTION_LINE = re.compile(r"(?m)^\s*-\s+")
_JARGON = re.compile(
    r"(?i)\b(archivo|no inventados|QR:fake|grounding|bbe_ok|service role)\b"
)
_VOSEO = re.compile(r"(?i)\b(decime|querés|tenés|buscás|mostrame|armame)\b")
_QUESTION = re.compile(r"\?")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class CaseResult:
    case_id: str
    failure: str
    ok: bool
    checks: list[CheckResult] = field(default_factory=list)
    last_reply: str = ""
    replies: list[str] = field(default_factory=list)

    @property
    def failed_names(self) -> list[str]:
        return [c.name for c in self.checks if not c.ok]


def corpus_path() -> Path:
    return Path(__file__).resolve().parent / "corpus.json"


def load_corpus() -> dict[str, Any]:
    return json.loads(corpus_path().read_text(encoding="utf-8"))


def option_line_count(text: str) -> int:
    return len(_OPTION_LINE.findall(text))


def score_reply(text: str, expect: dict[str, Any]) -> list[CheckResult]:
    """Apply expect block + named criteria checks to the last Adri reply."""
    results: list[CheckResult] = []
    lowered = text.lower()

    for needle in expect.get("last_must_contain") or []:
        results.append(
            CheckResult(
                f"contains:{needle}",
                needle.lower() in lowered,
                f"missing {needle!r}" if needle.lower() not in lowered else "",
            )
        )

    any_needles = expect.get("last_must_contain_any") or []
    if any_needles:
        ok = any(n.lower() in lowered for n in any_needles)
        results.append(
            CheckResult(
                "contains_any",
                ok,
                f"none of {any_needles}" if not ok else "",
            )
        )

    for needle in expect.get("last_must_not_contain") or []:
        results.append(
            CheckResult(
                f"not_contains:{needle}",
                needle.lower() not in lowered,
                f"found {needle!r}" if needle.lower() in lowered else "",
            )
        )

    for pattern in expect.get("last_must_match") or []:
        ok = bool(re.search(pattern, text))
        results.append(CheckResult(f"match:{pattern}", ok, "no match" if not ok else ""))

    for pattern in expect.get("last_must_not_match") or []:
        ok = not bool(re.search(pattern, text))
        results.append(CheckResult(f"not_match:{pattern}", ok, "matched" if not ok else ""))

    if "option_lines_max" in expect:
        count = option_line_count(text)
        limit = int(expect["option_lines_max"])
        results.append(
            CheckResult(
                "option_lines_max",
                count <= limit,
                f"{count}>{limit}" if count > limit else "",
            )
        )

    named = set(expect.get("checks") or [])
    if "no_internal_jargon" in named:
        hit = _JARGON.search(text)
        results.append(
            CheckResult(
                "no_internal_jargon",
                hit is None,
                f"jargon {hit.group(0)!r}" if hit else "",
            )
        )
    if "address_tu" in named:
        hit = _VOSEO.search(text)
        results.append(
            CheckResult(
                "address_tu",
                hit is None,
                f"voseo {hit.group(0)!r}" if hit else "",
            )
        )
    if "has_advance_question" in named:
        ok = bool(_QUESTION.search(text))
        results.append(CheckResult("has_advance_question", ok, "no ?" if not ok else ""))
    if "max_three_options" in named:
        count = option_line_count(text)
        results.append(
            CheckResult(
                "max_three_options",
                count <= 3,
                f"{count}>3" if count > 3 else "",
            )
        )
    if "respects_budget" in named:
        bad = "descuento inventado" in lowered or "20%" in text
        results.append(CheckResult("respects_budget", not bad, "discount invent" if bad else ""))
    if "answers_request" in named:
        results.append(CheckResult("answers_request", bool(text.strip()), "empty reply"))
    if "no_repeat_list" in named:
        dumping = bool(re.search(r"(?i)encontr[eé] estas opciones", text))
        results.append(
            CheckResult("no_repeat_list", not dumping, "re-listed options" if dumping else "")
        )

    return results


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.ok)
    by_failure: dict[str, dict[str, int]] = {}
    criterion_totals: dict[str, list[int]] = {}
    named_criteria = {
        "answers_request",
        "no_repeat_list",
        "respects_budget",
        "max_three_options",
        "has_advance_question",
        "no_internal_jargon",
        "address_tu",
    }
    for case in results:
        bucket = by_failure.setdefault(case.failure, {"pass": 0, "fail": 0})
        bucket["pass" if case.ok else "fail"] += 1
        for check in case.checks:
            if check.name not in named_criteria:
                continue
            stats = criterion_totals.setdefault(check.name, [0, 0])
            stats[1] += 1
            if check.ok:
                stats[0] += 1
    return {
        "cases": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "by_failure": by_failure,
        "criteria": {
            name: {"ok": ok, "n": n, "rate": round(ok / n, 4) if n else 0.0}
            for name, (ok, n) in sorted(criterion_totals.items())
        },
        "failed_ids": [r.case_id for r in results if not r.ok],
    }
