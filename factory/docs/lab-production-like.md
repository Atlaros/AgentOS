# Lab production-like (Factory ↔ AgentOS)

Cómo probar el cableado local como si fuera producción, **sin tocar la cafetería viva**.

## Qué está permitido

| Pieza | Puerto / destino | Notas |
| --- | --- | --- |
| Factory Postgres | `127.0.0.1:5434` | Compose `db` en este repo |
| Factory API / panel | `:8000` / `:3000` | Lab only |
| AgentOS API | `127.0.0.1:8080` | Repo AgentOS aparte |
| AgentOS Postgres | `127.0.0.1:5433` | No es la base del café |

## Qué está prohibido

- Supabase o Render de la cafetería viva (`agent-ia-api`).
- Migraciones o prune contra una base remota del negocio vivo.
- Commitear `AGENTOS_API_KEY`, tokens Meta, o secretos en `.env`.

## Arranque Factory (lab)

```bash
docker compose up -d db
cp .env.example .env   # completar localmente; no commitear
# DATABASE_* → 127.0.0.1:5434
# APP_ENV=local  → seed + prune del piloto OK
# APP_ENV=production en lab nuevo → sync_seed=false (migra, no reescribe catálogo)
uv sync --extra dev
.venv/bin/uvicorn factory_os.api.main:app --app-dir apps/api --host 0.0.0.0 --port 8000
cd apps/web && npm install && npm run dev
```

Un host con punto (p.ej. `db.example.com`) en `APP_ENV=local|test` se rechaza antes de migrar. Loopback y el hostname Compose `db` siguen permitidos.

## Arranque AgentOS (lab)

En el checkout de AgentOS (no en este workspace):

```bash
docker compose up -d
uv sync --all-packages --group dev
uv run alembic upgrade head
uv run agentos-api   # :8080
```

## Cable Factory → AgentOS

En el `.env` de Factory (local, sin git):

```bash
AGENTOS_BASE_URL=http://127.0.0.1:8080
AGENTOS_ORGANIZATION_ID=<uuid del bootstrap>
AGENTOS_API_KEY=<api key del bootstrap>
```

Bootstrap (desde AgentOS, imprime org id; no pegues la key en chats ni docs):

```bash
# usa AGENTOS_BOOTSTRAP_TOKEN del .env de AgentOS
uv run python scripts/demo_local_surface.py
```

O el smoke de este repo:

```bash
export AGENTOS_BASE_URL=http://127.0.0.1:8080
export AGENTOS_BOOTSTRAP_TOKEN=...   # solo lab
.venv/bin/python scripts/smoke_factory_agentos_lab.py
```

### Contrato observado

1. Texto del cliente (`ya pagué`) **no** escribe el ledger de AgentOS.
2. Confirm del adaptador (`confirm_payment_from_adapter`) **sí** hace `POST /v1/fiat-settlements` con `Idempotency-Key` = `provider_ref`.
3. Un AgentOS caído no deshace el confirm local en Factory.
4. Replay del mismo `provider_ref` es idempotente en AgentOS.

## Deploy lab (si hay)

- Servicio Render **nuevo** / entorno nuevo de Factory.
- **No** reutilizar `agent-ia-api` ni el Supabase del café.
- Checklist: migraciones solo contra DB de lab; `sync_seed=false` en production-like; remote host refused en `APP_ENV=local`.

## Roster de empleados (ADR-026)

Consola `/operator` → Employees; dueño en `/owner`. Sales y collections no se apagan. Clones = `base_role` del catálogo, sin tools nuevas.
