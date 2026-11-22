# Turn from published flow map

WhatsApp turn graph follows the tenant's published canvas map (docs/00 item 4). Branch `factory/phase-1-isolation`. Runner: `.venv/bin/pytest -q`.

## Specs

S1. Pedido del owner, textual: "vamos en ese orden de lo falta que dice en el doc 00" — primero el hueco del ítem 4.

S2. Se puede publicar un mapa de lienzo por negocio (kinds del catálogo); sin publicación, el turno sigue usando los módulos (comportamiento actual).

S3. Con mapa publicado, `run_customer_turn` arma el grafo desde esos kinds (mismo mapper módulo→empleado); sin `cobros` en el mapa no hay nodo Cobros.

S4. El núcleo `pedido` + `cobros` no se puede publicar sin ellos (`path_locked`).

S5. docs/00 ítem 4 actualizado; tests verdes (memoria; Postgres si hay URL).

## Tasks

- [x] T1 — S2–S4. Publish map + turn wiring + tests. Route: inline. GREEN `tests/test_published_flow_map.py`.
- [x] T2 — S5 + commit. Route: inline. Suite 700 passed / 1 skipped.

## Log

L1. 2026-11-19. "vamos en ese orden de lo falta que dice en el doc 00"
L2. T1 GREEN: `publish_flow_map` / `get_published_flow_kinds` / `graph_nodes_for_tenant`; `run_customer_turn` prefers published kinds; `POST /api/operator/flow-map/publish`; migration `060_published_flow_maps.sql`; docs/00 item 4 marked done.
