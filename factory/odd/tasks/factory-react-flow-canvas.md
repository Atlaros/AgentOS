# Factory React Flow canvas

Migrate `/operator/flow` drawing layer to `@xyflow/react` per ADR-025. Branch `factory/phase-1-isolation`. Runner: `.venv/bin/pytest -q` (backend unchanged) + `cd apps/web && npm run build`.

## Specs

S1. Pedido del owner, textual: "continua" sobre docs/00 ítem 5 / ADR-025: lienzo con React Flow.

S2. `tests/test_flow_canvas.py` sigue verde sin cambios de contrato.

S3. `flow-board.tsx` dibuja nodos y aristas con `@xyflow/react`; zoom/paneo de la librería; la validación de conexiones sigue usando `compatible` del servidor.

S4. El núcleo bloqueado (`locked`) no se borra desde el lienzo; una conexión a puerto incompatible no se crea.

S5. docs/00 ítem 5 actualizado a primer corte (falta panel de propiedades / Probar / asistente).

## Tasks

- [x] T1 — S3. Instalar `@xyflow/react` y migrar el tablero. Route: inline.
- [x] T2 — S4. isValidConnection + nodos locked no deletables. Route: inline.
- [x] T3 — S2 + S5 + suite + build + commit. Route: inline. `test_flow_canvas` 12/2; `npm run build` ok.

## Log

L1. 2026-11-19. "continua" (tras cerrar turno por módulos).
L2. 2026-11-19. Migrated flow-board to React Flow 12.12.1; tsc clean; test_flow_canvas 12 passed / 2 skipped.
