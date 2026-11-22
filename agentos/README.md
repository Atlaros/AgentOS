# AgentOS

Financial layer of **Factory AgentOS** (this repo’s [`agentos/`](../) folder). Open financial infrastructure for AI agents and businesses — wallets, policy, ledger, REST/SDK/MCP.

Factory (the SMB agent factory) lives next door in [`../factory/`](../factory/).

**Jury-facing network demo:** **Stellar Testnet** (native XLM). Same path as Fake: link wallet → payment request → policy (human approve when required) → transfer → ledger — with a Horizon-confirmed `network_tx_id`.

Fake remains the default for **offline CI** and machines without a lab signer.

## Stellar Testnet evidence

| | |
| --- | --- |
| Account | [`GDNGAFUJ4S7JELRSJXQ3MFOIPPXC636S7D2S7JSCN5NUSA66MFKNQ7U6`](https://stellar.expert/explorer/testnet/account/GDNGAFUJ4S7JELRSJXQ3MFOIPPXC636S7D2S7JSCN5NUSA66MFKNQ7U6) |
| 1 XLM payment | [`e44b97333a1567d954d583ee29c2b9700b627301afb28979339c6ad7157ca72d`](https://stellar.expert/explorer/testnet/tx/e44b97333a1567d954d583ee29c2b9700b627301afb28979339c6ad7157ca72d) |
| Runbook | [`docs/lab-stellar-testnet.md`](docs/lab-stellar-testnet.md) |

```bash
export AGENTOS_STELLAR_SECRET_KEY=S...   # same value used to start the API; never commit
uv run python scripts/demo_stellar_api.py
```

No private keys are stored in the application database. Mainnet is denied by the adapter.

### Why Stellar (café → supplier)

Under Factory’s autonomy floor, an agent may request “pay supplier”. AgentOS policy either auto-allows within the lab cap or requires a human. The Stellar adapter then submits Testnet XLM and the ledger keeps the hash — so settlement is not a sentence in WhatsApp. See the root [`README.md`](../README.md#why-stellar-concrete-café-case).

## Status

- Phase 1 docs: [`docs/`](docs/)
- Decisions locked: [`docs/riesgos-y-decisiones.md`](docs/riesgos-y-decisiones.md)
- Sunday E2E tracking: [`odd/tasks/sunday-e2e-demo.md`](odd/tasks/sunday-e2e-demo.md)
- Stage for hackathon review: **MVP / lab** (not production mainnet)

## Quick start (lab)

```bash
cp .env.example .env
docker compose up -d
uv sync --all-packages --group dev
uv run alembic upgrade head
uv run agentos-api
# other terminal (Fake path, no signer):
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
- `apps/mcp` — MCP server (tools call SDK → same policy)
- `packages/agentos` — domain modules (identity, wallets, ops, policy, ledger, adapters)
- `packages/agentos_sdk` — thin Python client
- `examples/pilot_agent_ia_client.py` — Phase 8 Agent-IA-shaped consumer (no Agent-IA repo edits)
- `migrations` — Alembic from `001` (new schema; not Factory)
- `docs/` — ADRs and architecture

## Phase 8 pilot (Agent-IA-shaped client)

With API running:

```bash
uv run python examples/pilot_agent_ia_client.py
```

## MCP

```bash
export AGENTOS_BASE_URL=http://127.0.0.1:8080
export AGENTOS_API_KEY=...
export AGENTOS_ORGANIZATION_ID=...
uv run agentos-mcp
```

## Out of scope (for now)

Custody · Mainnet · Fiat/Baneco inside AgentOS · commerce UI · billing charges  
(Factory/WhatsApp/caja live in [`../factory/`](../factory/); this package stays the money rail.)
