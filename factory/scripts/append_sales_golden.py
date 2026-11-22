#!/usr/bin/env python3
"""Append a sales-quality golden case from a failed pilot turn (T16).

Does not invent Closet facts. Owner supplies customer text + Adri reply + failure tag.

  .venv/bin/python scripts/append_sales_golden.py \\
    --failure F11 \\
    --id sq_26_f11_re_greet \\
    --customer 'hola' \\
    --reply '¡Hola! ¿Cómo estás? Te paso…' \\
    --must-not '¡Hola!' \\
    --checks no_repeat_list,address_tu
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evals" / "sales_quality" / "corpus.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failure", required=True, help="Failure id e.g. F11")
    parser.add_argument("--id", required=True, help="Case id e.g. sq_26_f11_…")
    parser.add_argument("--customer", required=True, action="append", help="Customer turn (repeatable)")
    parser.add_argument("--reply", default="", help="Observed bad/good Adri reply (documentation)")
    parser.add_argument("--must-contain", default="", help="Comma-separated needles")
    parser.add_argument("--must-not", default="", help="Comma-separated needles")
    parser.add_argument("--checks", default="no_internal_jargon,address_tu", help="Comma-separated checks")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    ids = {c["id"] for c in corpus["cases"]}
    if args.id in ids:
        print(f"case id already exists: {args.id}", file=sys.stderr)
        return 1

    expect: dict = {"checks": [c.strip() for c in args.checks.split(",") if c.strip()]}
    if args.must_contain:
        expect["last_must_contain"] = [x.strip() for x in args.must_contain.split(",") if x.strip()]
    if args.must_not:
        expect["last_must_not_contain"] = [x.strip() for x in args.must_not.split(",") if x.strip()]

    case = {
        "id": args.id,
        "failure": args.failure,
        "title": args.id.replace("_", " "),
        "turns": [{"role": "customer", "text": text} for text in args.customer],
        "expect": expect,
        "pilot_note": (args.reply or "").strip()[:500] or None,
    }
    if case["pilot_note"] is None:
        del case["pilot_note"]

    if args.dry_run:
        print(json.dumps(case, ensure_ascii=False, indent=2))
        return 0

    corpus["cases"].append(case)
    corpus["counts"] = {"cases": len(corpus["cases"])}
    CORPUS.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"appended {args.id}; corpus now {len(corpus['cases'])} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
