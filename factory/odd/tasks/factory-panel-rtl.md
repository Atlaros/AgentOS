# Panel RTL tests

Close docs/00 item 6 — DOM/RTL coverage for the operator panel. Branch `factory/phase-1-isolation`. Runner: `cd apps/web && npm test`.

## Specs

S1. Pedido del owner: "vamos en ese orden de lo falta que dice en el doc 00" — ítem 6 tras el 5.

S2. Vitest runs at least one React Testing Library (jsdom) test against a real panel component (not only pure helpers).

S3. Existing pure Vitest suites stay green; docs/00 ítem 6 updated.

## Tasks

- [x] T1 — S2. RTL setup + properties panel component test. Route: inline. 24 Vitest passed.
- [x] T2 — S3 + commit. Route: inline.

## Log

L1. 2026-11-19. "vamos en ese orden de lo falta que dice en el doc 00"
L2. Added jsdom + @testing-library/react; FlowPropertiesPanel + flow-properties.test.tsx.
