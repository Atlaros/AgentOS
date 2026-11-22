# Factory template evals

Fase 3 de ADR-017, decidida en ADR-020. Rama `factory/phase-1-isolation`. Entrega `stacked-to-main`. Runner: `.venv/bin/pytest -q evals/test_cafe_golden.py evals/test_template_exit.py evals/test_closet_golden.py`.

## Specs

S1. ADR-017 fase 3, textual: "Evals por plantilla y lista de salida." Resultado: "Una mejora del núcleo no rompe un rubro ya probado. Los tests de Closet siguen verdes."

S2. ADR-020: golden por plantilla, lista de salida en `evals/template_exit.py`, `make_eval_shop(industry=...)`.

## Tasks

- [x] T1 — ADR-020 y tarea ODD.
- [x] T2 — `make_eval_shop(industry=)` + lista de salida + golden café. Closet sigue verde. 5 passed.

## Log

L1. 2026-11-18. Continuación tras aprovisionamiento.

L2. Café golden: buscar por nombre (`empanadas`), no por código solo — `quiero c001` salta a Cobros.
