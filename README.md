# AgentOS

Open financial infrastructure for AI agents and businesses — independent of Factory Agent OS and Agent-IA V2.

**MVP heart (Sunday demo):** an external agent can **link/query a wallet → create a payment request → pass policy (human approve when required) → execute a Fake transfer → read the ledger**, via REST.

First real network (stretch): Stellar Testnet. No private keys stored in the application database.

## Status

- Phase 1 docs: [`docs/`](docs/)
- Decisions locked: [`docs/riesgos-y-decisiones.md`](docs/riesgos-y-decisiones.md)
- Sunday E2E tracking: [`odd/tasks/sunday-e2e-demo.md`](odd/tasks/sunday-e2e-demo.md)

## Quick start (lab)

```bash
cp .env.example .env
docker compose up -d
uv sync --all-packages --group dev
uv run alembic upgrade head
uv run agentos-api
# other terminal:
./scripts/demo_e2e.sh
```

API listens on `0.0.0.0:8080`. Postgres on host port **5433** (avoids clashing with Factory).

## Tests

```bash
uv run pytest tests/unit -q
AGENTOS_RUN_INTEGRATION=1 uv run pytest -q
```

## Layout

- `apps/api` — FastAPI entrypoint
- `packages/agentos` — domain modules (identity, wallets, ops, policy, ledger, fake adapter)
- `migrations` — Alembic from `001` (new schema; not Factory)
- `docs/` — ADRs and architecture

## Stellar Testnet (stretch)

Fake is the default Sunday demo. Optional real Testnet path: see [`docs/lab-stellar-testnet.md`](docs/lab-stellar-testnet.md).

## Out of scope (for now)

Custody · Mainnet · Fiat/Baneco · MCP (next) · Factory/Agent-IA code changes · commerce UI

