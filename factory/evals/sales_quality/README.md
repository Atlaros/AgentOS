# Sales quality evals

Corpus de ~25 conversaciones derivadas de F1–F8 (Closet). Mide calidad comercial, no solo grounding.

## Correr reglas deterministas

```bash
.venv/bin/pytest -q evals/test_sales_quality.py
# o
.venv/bin/python -c "from evals.sales_quality.runner import run_corpus; import json; print(json.dumps(run_corpus()[1], indent=2))"
```

Baseline: [`baseline.json`](baseline.json) (FakeGateway + catálogo Closet).

Fase 2 re-measure: [`fase2.json`](fase2.json) — `scripts/measure_sales_fase2.py`.

Piloto WhatsApp (T16): [`PILOT.md`](PILOT.md).

## Juez LLM (no pytest)

```bash
.venv/bin/python scripts/judge_sales_quality.py --dry-run
# con Gemini:
MODEL_PROVIDER=gemini .venv/bin/python scripts/judge_sales_quality.py
```

## Criterios

`answers_request`, `no_repeat_list`, `respects_budget`, `max_three_options`, `has_advance_question`, `no_internal_jargon`, `address_tu`.
