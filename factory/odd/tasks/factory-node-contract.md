# Factory node contract

Un solo contrato de nodo en `packages/contracts`. Rama `factory/phase-1-isolation`. Entrega local. Runner: `.venv/bin/pytest -q`.

## Specs

S1. Pedido del owner, textual: "xontinua" sobre docs/00 ítem 1: "Contrato de nodo único. Puertos, módulo, piso de autonomía y rubros de cada nodo en packages/contracts."

S2. `factory_os.contracts.nodes` define cada nodo: kind, ports in/out, module, autonomy floor, industries, core.

S3. `flow_canvas` lee ese catálogo. No duplica `_NODE_PORTS`. Tests de barandas siguen verdes.

S4. Un kind desconocido no entra a la paleta. `pago_confirmado` solo sale de Cobros.

## Tasks

- [x] T1 — S2. Catálogo en contracts + exports. Route: inline.
- [x] T2 — S3, S4. flow_canvas consume el catálogo + tests. Route: inline.
- [x] T3 — docs/00, 01, 02 + suite + commit. Route: inline. Commit: 9662a0a. 662 passed, 19 skipped.

## Log

L1. 2026-11-19. "xontinua"
