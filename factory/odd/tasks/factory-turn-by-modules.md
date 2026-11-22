# Factory turn graph by modules

El turno de WhatsApp se arma con los módulos del negocio. Rama `factory/phase-1-isolation`. Runner: `.venv/bin/pytest -q`.

## Specs

S1. Pedido del owner, textual: "continua" sobre docs/00 ítem 4: "El turno se arma por negocio."

S2. Sin módulos configurados (piloto legacy) el grafo sigue con Adri, Cobros, Operaciones y Postventa.

S3. Si el negocio no tiene el módulo `cobros`, el grafo no incluye el nodo Cobros y el orquestador no enruta ahí.

S4. Con `cobros` activo, el encadenamiento Adri → Cobros en el mismo turno sigue funcionando.

## Tasks

- [x] T1 — S2–S3. `graph_nodes_for_modules` + grafo parametrizado + tests. Route: inline.
- [x] T2 — S4 + wiring en `run_customer_turn` con `tenant_config`. Route: inline.
- [x] T3 — docs/00 + suite + commit. Route: inline. Suite: 673 passed / 19 skipped.

## Log

L1. 2026-11-19. "continua"
L2. 2026-11-19. Wired `build_turn_graph` / `get_turn_graph` / `choose_employee(allowed_nodes)` / `run_customer_turn` + `ShopRuntime.database_url`. Tests in `tests/test_turn_by_modules.py`.
