# Factory AgentOS

**Factory AgentOS** is Atlaros’ platform for small and mid-sized businesses that want AI employees with real wallets, payments, and guarded automation — not a chatbot bolted onto a spreadsheet.

This repository ships **both layers** reviewers need in one place:

| Folder | Product | What it does |
| --- | --- | --- |
| [`factory/`](factory/) | **Factory Agent OS** | Agent factory for cafés and clothing stores: WhatsApp sales, catalog, orders, cash, canvas, autonomy floor, operator console |
| [`agentos/`](agentos/) | **AgentOS** | Open financial infrastructure for agents: wallets, policy, ledger, REST/SDK/MCP, Stellar Testnet first |

Factory runs the commercial conversation and proposes actions. AgentOS authorizes money movement. Customer chat never confirms a payment.

## Why two folders

They stay **separate codebases** with clear boundaries (RLS tenants in Factory; org isolation in AgentOS). Putting them in one repo is for **review and lab demos** so you can read both without juggling remotes.

Canonical long-term homes:

- Factory development also continues in `Factory-Agent-OS-next` when that remote is used.
- AgentOS development lives under `agentos/` here (`https://github.com/Atlaros/AgentOS`).

## Quick map

```text
Factory AgentOS
├── factory/     SMB agent factory (Operator, canvas, motor modules)
└── agentos/     Financial rails (wallets, policy, ledger, MCP)
```

## Run the lab (local)

### 1. AgentOS (money)

```bash
cd agentos
cp .env.example .env
docker compose up -d
uv sync --all-packages --group dev
uv run alembic upgrade head
uv run agentos-api
# API: 0.0.0.0:8080  ·  Postgres host port 5433
```

See [`agentos/README.md`](agentos/README.md) for tests, MCP, and the Stellar lab notes.

### 2. Factory (agents + shop)

```bash
cd factory
cp .env.example .env   # never commit secrets
uv sync --extra dev
docker compose up -d db   # Factory Postgres on 5434 when using compose
.venv/bin/pytest -q
cd apps/web && npm install && npm run dev   # panel :3000
```

See [`factory/AGENTS.md`](factory/AGENTS.md) and [`factory/docs/00-vision-y-estado.md`](factory/docs/00-vision-y-estado.md).

Wire Factory → AgentOS with the lab smoke helper when both stacks are up:

```bash
cd factory
# configure AGENTOS_* in .env, then:
python scripts/smoke_factory_agentos_lab.py
```

## Invariants (both products)

- Tenant / org identity comes from the **runtime**, never from model text.
- The LLM does not receive database URLs, service roles, or raw SQL.
- Money, stock, orders, and journal entries keep a **human-approval floor**.
- `pago_confirmado` / settlement confirmation only comes from payment adapters — never from customer chat.

## Docs worth reading first

- Factory vision & phase status: [`factory/docs/00-vision-y-estado.md`](factory/docs/00-vision-y-estado.md)
- Factory architecture: [`factory/docs/01-arquitectura.md`](factory/docs/01-arquitectura.md)
- AgentOS architecture: [`agentos/docs/arquitectura.md`](agentos/docs/arquitectura.md)
- AgentOS decisions: [`agentos/docs/riesgos-y-decisiones.md`](agentos/docs/riesgos-y-decisiones.md)
- Pitch / capability audit (lab snapshot): [`docs/pitch-deck-research.md`](docs/pitch-deck-research.md)

## License / status

Lab and review build. Do not point this pack at a live café database or production secrets.
