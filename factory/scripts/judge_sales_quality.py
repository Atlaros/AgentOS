#!/usr/bin/env python3
"""LLM judge for sales-quality corpus. Does NOT run inside pytest.

Usage:
  MODEL_PROVIDER=gemini .venv/bin/python scripts/judge_sales_quality.py
  .venv/bin/python scripts/judge_sales_quality.py --dry-run   # print prompts only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.sales_quality.runner import run_corpus  # noqa: E402


RUBRIC = """Sos un juez de calidad de venta por WhatsApp (Authentic Closet / Adri).
Puntúa 0 o 1 cada criterio sobre la ÚLTIMA respuesta del agente:
- answers_request
- no_repeat_list
- respects_budget (si aplica; si no aplica, 1)
- max_three_options
- has_advance_question
- no_internal_jargon
- address_tu (español de tú, no voseo)
Respondé SOLO JSON: {"scores":{"answers_request":0|1,...},"notes":"..."}
"""


def _judge_one(case_id: str, transcript: str, last_reply: str) -> dict:
    from factory_os.harness.model_gateway import GatewaySettings, build_gateway

    settings = GatewaySettings()
    if not (settings.google_api_key or os.environ.get("GOOGLE_API_KEY")):
        return {"skipped": True, "reason": "no GOOGLE_API_KEY"}
    gateway = build_gateway(settings)
    prompt = (
        f"{RUBRIC}\ncase={case_id}\ntranscript:\n{transcript}\n\n"
        f"última respuesta:\n{last_reply}\n"
    )
    # Reuse draft path as a free-form complete via Fake/Failover internals is awkward;
    # call the first HTTP provider if present.
    providers = getattr(gateway, "_providers", None)
    if not providers:
        return {"skipped": True, "reason": "no network provider (MODEL_PROVIDER=fake?)"}
    text, provider, latency_ms, tokens, _fb, err = gateway._complete(prompt)  # noqa: SLF001
    if not text:
        return {"skipped": True, "reason": err or "empty", "provider": provider}
    try:
        start = text.find("{")
        end = text.rfind("}")
        payload = json.loads(text[start : end + 1])
    except Exception:  # noqa: BLE001
        return {"raw": text, "provider": provider, "parse_ok": False}
    payload["provider"] = provider
    payload["latency_ms"] = latency_ms
    payload["tokens"] = tokens
    payload["parse_ok"] = True
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    results, summary = run_corpus()
    if args.limit:
        results = results[: args.limit]

    judgments = []
    for case in results:
        transcript = "\n".join(f"Adri: {r}" for r in case.replies[:-1]) + f"\nAdri*: {case.last_reply}"
        if args.dry_run:
            judgments.append({"case_id": case.case_id, "dry_run": True, "last_reply": case.last_reply})
            continue
        judgments.append({"case_id": case.case_id, "deterministic_ok": case.ok, **_judge_one(case.case_id, transcript, case.last_reply)})

    out = {"deterministic": summary, "judgments": judgments}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
