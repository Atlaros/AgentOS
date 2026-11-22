# Factory provisioning

Fase 2 de ADR-017, decidida en ADR-019. Rama `factory/phase-1-isolation` (pila stacked-to-main; la fase 2 sigue en commits encima). Entrega `stacked-to-main`. Runner: `.venv/bin/pytest -q tests/test_provision_business.py`.

## Specs

S1. ADR-017 fase 2, textual: "Aprovisionamiento: un comando crea un negocio desde una plantilla, con permisos y autonomía por negocio." Resultado: "Un negocio nuevo del mismo rubro en horas, sin código nuevo."

S2. ADR-019: plantilla `cafe` o `ropa`; escribe industry y módulos; con base, siembra el catálogo como ese tenant.

S3. Owner: siete fases en código, ODD/TDD, `stacked-to-main`, sin freno de cliente real.

## Tasks

- [x] T1 — ADR-019 y tarea ODD. Cubre S1, S3. Inline. Commit: b9657e6.
- [x] T2 — `provision_business` en memoria: industry + módulos de plantilla. Cubre S2 (sin DB). RED ImportError → GREEN 2 passed. Risk: none. Commit: b9657e6.
- [x] T3 — sembrar catálogo en Postgres como el tenant nuevo. Cubre S2 (con DB). Código en `provision._seed_catalog`; test skip sin DB. Risk: item 1. Commit: 13b0c33.
- [x] T4 — piso de autonomía de plantilla, visible en la consola. Confirmar pago queda en never; aflojarlo falla. Sin migración y sin cambiar la autorización del runtime. Risk: none. Commit: 4fa4cbd.

## Log

L1. 2026-11-18. Continuación del plan de siete fases tras cerrar aislamiento.

L2. T1+T2 GREEN. Commit b9657e6.

L3. T3 test skippable + seed path. 2 passed, 1 skipped. Commit 13b0c33. Siguiente fase: 3 evals por plantilla.

L4. 2026-11-18. T4 autonomía de plantilla. RED ModuleNotFoundError. El dueño puede pedir más cuidado y no puede aflojar «nunca» en confirmar pago.
