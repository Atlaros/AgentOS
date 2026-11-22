# Lienzo completo (properties, try, publish, assistant)

Close docs/00 item 5 gaps on `/operator/flow`. Branch `factory/phase-1-isolation`. Runner: `.venv/bin/pytest -q` + `cd apps/web && npm test`. Delivery: ask-on-risk.

## Specs

S1. Pedido del owner, textual: "vamos en ese orden de lo falta que dice en el doc 00" — ítem 5 tras el 4.

S2. Panel de propiedades: al seleccionar un nodo del lienzo se muestra kind, locked y puertos compatibles; sin código. Layout paleta | lienzo | propiedades (ADR-017).

S3. Probar antes de publicar: valida kinds en el servidor sin persistir; Publicar llama `POST /api/operator/flow-map/publish` con `tenant_id` y kinds del canvas; núcleo `pedido`+`cobros` requerido (`path_locked`).

S4. Asistente: propone cambios de mapa/reglas sin publicar solo (propuesta ≠ publish).

S5. `tests/test_flow_canvas.py` y `flow-guards.test.ts` verdes; docs/00 ítem 5 actualizado al cerrar.

## Tasks

- [x] T1 — S2. Properties panel + selection. Route: inline.
- [x] T2 — S3. Try + Publish footer wired to API. Route: inline.
- [x] T3 — S4. Propose-without-publish assistant. Route: inline.
- [x] T4 — S5 + docs/00 + commit. Route: inline. Suite + Vitest green.

## Log

L1. 2026-11-19. "vamos en ese orden de lo falta que dice en el doc 00"
L2. T1–T3: properties on selection; Try/Publish/Propose endpoints + UI; Vitest guards extended.
