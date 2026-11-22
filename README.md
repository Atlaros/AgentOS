# Factory AgentOS

### AI employees that sell. Financial rails that don’t lose control of the money.

**Factory AgentOS** is Atlaros’ platform for entrepreneurs and SMEs that already close deals on WhatsApp — and need technology that can **attend, sell, collect, and settle** without turning the business into a black box.

One product. Two layers. One repository for review.

| Layer | Folder | Job |
| :---: | --- | --- |
| **Business OS** | [`factory/`](factory/) | Digital employees, catalog, orders, cash, WhatsApp, operator console, guarded flow canvas |
| **Financial OS** | [`agentos/`](agentos/) | Wallets, policy, human approval, ledger, REST · SDK · MCP — Stellar Testnet first |

> The model proposes. The runtime decides. **Customer chat never confirms a payment.**

---

## The problem we solve

Small and mid-sized businesses (starting with **cafés** and **clothing stores**) run on chat, cash, and trust. Generic chatbots invent prices, “confirm” payments in text, and can’t be audited. Banks and blockchains don’t speak WhatsApp. Owners need **hybrid workforce**: humans + agents — with a hard floor on money, stock, and accounting.

## What Factory AgentOS is

```text
Customer (WhatsApp / counter)
        │
        ▼
┌─────────────────── factory/ ───────────────────┐
│  Digital employees · catalog · orders · caja   │
│  Autonomy floor · Operator · React Flow canvas │
└──────────────────────┬─────────────────────────┘
                       │ settlement (lab)
                       ▼
┌─────────────────── agentos/ ───────────────────┐
│  Wallet → payment request → policy → approve   │
│  → transfer → ledger   (REST / SDK / MCP)      │
└────────────────────────────────────────────────┘
```

| Capability | Why it matters to the business |
| --- | --- |
| **Digital employees** | Roles (sales, collections, ops…) per tenant — not one anonymous bot |
| **Guarded canvas** | Publish validated flows; never arbitrary SQL or free-form payment confirm |
| **Autonomy floor** | Owner can tighten permissions; cannot loosen money/stock/ledger below the floor |
| **Agent money path** | Link wallet → request → policy → optional human approve → execute → ledger |
| **Clear blast radius** | Factory tenants (RLS) and AgentOS orgs stay isolated codebases |

---

## Who it’s for

- **Owners** who want agents on WhatsApp without losing the cash register  
- **Operators / agencies** provisioning several businesses from templates  
- **Builders** who need agent-native financial APIs (REST, SDK, MCP) on Stellar Testnet  

First verticals in Factory: **café** and **ropa**. AgentOS stays vertical-agnostic infrastructure.

---

## Repository map

```text
Factory AgentOS/
├── factory/     ← SMB agent factory (panel, APIs, agents, canvas)
├── agentos/     ← financial infrastructure for agents
└── docs/        ← pitch / capability audit for reviewers
```

They are **separate products with a shared story**. This monorepo exists so reviewers can inspect both without switching remotes.

---

## Start here (reviewers)

1. **Product narrative & honesty audit** → [`docs/pitch-deck-research.md`](docs/pitch-deck-research.md)  
2. **Factory vision & phase status** → [`factory/docs/00-vision-y-estado.md`](factory/docs/00-vision-y-estado.md)  
3. **AgentOS architecture & decisions** → [`agentos/docs/arquitectura.md`](agentos/docs/arquitectura.md) · [`agentos/docs/riesgos-y-decisiones.md`](agentos/docs/riesgos-y-decisiones.md)  
4. **Lab wiring Factory → AgentOS** → [`factory/docs/lab-production-like.md`](factory/docs/lab-production-like.md)

### Non-negotiables (read before demos)

- Tenant / organization identity comes from the **runtime**, never from model text  
- The LLM never receives database URLs, service roles, or raw SQL  
- Money, stock, orders, and journal entries keep a **human-approval floor**  
- Payment confirmation comes only from **adapters** — never from customer messages  

---

## Run the lab locally

### AgentOS — money path (`:8080`)

```bash
cd agentos
cp .env.example .env
docker compose up -d
uv sync --all-packages --group dev
uv run alembic upgrade head
uv run agentos-api
```

Postgres on host **5433**. Details, tests, MCP, Stellar lab: [`agentos/README.md`](agentos/README.md).

### Factory — agents & shop (`:3000` / `:8000`)

```bash
cd factory
cp .env.example .env          # never commit secrets
uv sync --extra dev
docker compose up -d db       # Postgres on 5434
.venv/bin/pytest -q
cd apps/web && npm install && npm run dev
```

Operator entry: [`factory/AGENTS.md`](factory/AGENTS.md).

### Both together

```bash
cd factory
# set AGENTOS_* in .env, then:
python scripts/smoke_factory_agentos_lab.py
```

---

## Status

| Area | Today |
| --- | --- |
| Factory motor (WhatsApp, cobros, caja, catalog…) | In production use at a real café pilot (live deploy is **out of scope** for this lab pack) |
| Factory platform (tenants, operator, canvas, roster) | Phased delivery — see vision doc |
| AgentOS MVP money path | Implemented (Fake adapter by default; Stellar Testnet when lab signer is set) |
| Mainnet / custody / full ramps | **Not** claimed — see readiness & roadmap in `agentos/docs/` |

This tree is a **lab and review build**. Do not point it at a live café database or production secrets.

---

## Atlaros

Built by **Atlaros** — Factory for the business conversation, AgentOS for the money rails, one brand for the hybrid workforce: **Factory AgentOS**.
