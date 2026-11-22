# Factory modules govern

Los módulos activos del negocio deciden mapa, navegación y APIs. Rama `factory/phase-1-isolation`. Entrega local. Runner: `.venv/bin/pytest -q`.

## Specs

S1. Pedido del owner, textual: "q sigue contiknua" sobre docs/00 «Qué falta» ítem 2: "Los módulos activos gobiernan de verdad."

S2. `GET /api/operator/flow-map?tenant_id=` arma el mapa con los módulos de ese negocio. Un módulo apagado no aparece (salvo el núcleo locked). Sin `tenant_id`, el query `modules=` sigue para tests y diagnóstico.

S3. Empty `enabled_modules` = sin restricción (piloto legacy). Non-empty = solo esos módulos (+ núcleo en el lienzo).

S4. El panel solo muestra pestañas de módulos activos; un GET a un módulo apagado responde 404 `module_disabled`.

S5. `/operator/flow` usa el `tenant_id` del query y la consola enlaza cada negocio a su lienzo.

## Tasks

- [x] T1 — S2, S3. API flow-map por tenant + test. Route: inline.
- [x] T2 — S4. Guard de módulos en API + nav del panel. Route: inline.
- [x] T3 — S5. UI operador. Route: inline.
- [x] T4 — Suite + docs/00 fila. Route: inline. Commit: 5d11888. 658 passed, 19 skipped.

## Log

L1. 2026-11-19. "q sigue contiknua"
