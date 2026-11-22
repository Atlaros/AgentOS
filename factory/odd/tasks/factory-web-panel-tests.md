# Factory web panel tests

Add a test runner for `apps/web` and cover the React Flow canvas guards from ADR-025. Branch `factory/phase-1-isolation`. Runner: `cd apps/web && npm test` + `.venv/bin/pytest -q tests/test_flow_canvas.py`.

## Specs

S1. Pedido del owner, textual: "primoer el testç" → primero tests del panel (`apps/web`).

S2. `apps/web` tiene runner (`npm test`) con Vitest.

S3. Un test prueba que una conexión a puerto incompatible no es válida (no se dibuja / `isValidConnection` false).

S4. Un test prueba que un nodo o arista `locked` no es borrable.

S5. docs/00 ítem 6 y docs/03 actualizados; `tests/test_flow_canvas.py` sigue verde.

## Tasks

- [x] T1 — S2–S4. Extraer guards + Vitest + tests del lienzo. Route: inline.
- [x] T2 — S5 + commit. Route: inline. `npm test` 5 passed; `test_flow_canvas` 12/2.

## Log

L1. 2026-11-19. "primoer el testç"
L2. 2026-11-19. Vitest 3.2.4 + flow-guards.ts/test; docs/00 ítem 6 y docs/03.
