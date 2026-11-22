#!/usr/bin/env python3
"""Fase 2 (T14–T15): measure fallback rates and compare sales-quality vs baseline.

  .venv/bin/python scripts/measure_sales_fase2.py
  .venv/bin/python scripts/measure_sales_fase2.py --print-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.sales_quality.measure import build_fase2_report, write_fase2_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-only", action="store_true", help="Do not write fase2.json")
    args = parser.parse_args()
    report = build_fase2_report() if args.print_only else write_fase2_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    ok = bool(report.get("vs_baseline", {}).get("no_regression"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
