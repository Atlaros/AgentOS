# Factory Postgres tests

Run the skipped Factory DB tests against a dedicated local Postgres, never the live café. Branch `factory/phase-1-isolation`. Runner: `FACTORY_OS_TEST_DATABASE_URL=… .venv/bin/pytest -q`.

## Specs

S1. Pedido del owner, textual: "hazlo test priemro" → pruebas con Postgres primero (docs/00 ítem 7).

S2. Con `docker compose up -d db` y `FACTORY_OS_TEST_DATABASE_URL` apuntando a una base de test dedicada, los tests que antes se saltaban corren en verde.

S3. `.env.example` y docs documentan la URL de test; nunca la base del negocio vivo.

S4. docs/00 ítem 7 actualizado.

## Tasks

- [x] T1 — S2. Levantar db de test + correr/arreglar tests Postgres. Route: inline. 79 passed with FACTORY_OS_TEST_DATABASE_URL.
- [x] T2 — S3–S4 + commit. Route: inline.

## Log

L1. 2026-11-19. "hazlo test priemro"
L2. 2026-11-19. Fixed split_sql comment `;`, registered migrations 047–049, tenant-scoped retain + catalog reads, seed no longer overwrites tenant name.
