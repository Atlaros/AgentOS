# Panel coverage + digest rule

More Vitest coverage in `apps/web`, and run the owner digest as a published catalog rule. Branch `factory/phase-1-isolation`. Runners: `cd apps/web && npm test` · `.venv/bin/pytest -q tests/test_rule_runtime.py tests/test_flow_canvas.py`.

## Specs

S1. Pedido del owner, textual: "Siguiente natural: más cobertura del panel, y enganchar eventos/digest de reglas."

S2. Tests Vitest extras para helpers puros del panel (`suppliers-tab`, `api-base`, `media-url`, `export-links` o equivalente).

S3. Regla publicada `owner_digest` + umbral con alertas + `notify_owner` dispara el digest de analítica (ADR-017 resumen al dueño), sin confirmar pagos, idempotente por día de negocio.

S4. docs/00 ítems 3 y 6 actualizados; suite relevante verde.

## Tasks

- [x] T1 — S2. Más tests del panel. Route: inline. `npm test` 18 passed.
- [x] T2 — S3. Digest como regla en `rule_runtime` + tests. Route: inline.
- [x] T3 — S4 + commit. Route: inline.

## Log

L1. 2026-11-19. "Siguiente natural: más cobertura del panel, y enganchar eventos/digest de reglas."
L2. 2026-11-19. Vitest helpers + owner_digest→notify_owner via analytics digest.
