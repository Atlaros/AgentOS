# Factory AgentOS

### AI employees that sell. Financial rails that don’t lose control of the money.

**Stage (verifiable):** **MVP / lab prototype** for the Stellar hackathon jury — not a claimed “live product with active users” for the full Factory AgentOS stack.  
**Pilot language (single phrase):** a **Santa Cruz café is identified as the first business pilot candidate**; Factory’s commerce motor has been exercised in that real-business context, while **AgentOS + Stellar Testnet settlement remains lab-proven** in this repository.

**Factory AgentOS** is Atlaros’ platform for entrepreneurs and SMEs that already close deals on WhatsApp — and need technology that can **attend, sell, collect, and settle** without turning the business into a black box.

One product. Two layers. One repository for review.

| Layer | Folder | Job |
| :---: | --- | --- |
| **Business OS** | [`factory/`](factory/) | Digital employees, catalog, orders, cash, WhatsApp, operator console, guarded flow canvas |
| **Financial OS** | [`agentos/`](agentos/) | Wallets, policy, human approval, ledger, REST · SDK · MCP — **Stellar Testnet evidenced below** |

> The model proposes. The runtime decides. **Customer chat never confirms a payment.**

---

## Why Stellar? (concrete café case)

Factory covers the visible café pain: WhatsApp orders, catalog, cash, and Baneco QR for **customer → business** collection.

AgentOS is for the other money direction — when a **digital employee** should move value **out** (supplier, remittance, settlement) without a free-form “yes, paid” in chat:

1. Agent creates a **payment request** (e.g. pay supplier up to a daily cap).  
2. **Policy** runs: under the autonomy floor → auto-allow; over the floor → **human approval**.  
3. Adapter executes on **Stellar Testnet** (native XLM in this MVP).  
4. **Ledger** stores the Horizon transaction id — audit trail the chat never invents.

That is why Stellar sits under Factory: same policy path as Fake, but with **network-confirmed** settlement the jury can open on [stellar.expert](https://stellar.expert).

USDC, Soroban, SEPs, and mainnet are **not** claimed in this MVP.

---

## Stellar Testnet — published evidence

Lab signer account (public only; secret never in git):

- **Account:** [`GDNGAFUJ4S7JELRSJXQ3MFOIPPXC636S7D2S7JSCN5NUSA66MFKNQ7U6`](https://stellar.expert/explorer/testnet/account/GDNGAFUJ4S7JELRSJXQ3MFOIPPXC636S7D2S7JSCN5NUSA66MFKNQ7U6)  
- **Payment (1 XLM, successful):** [`e44b97333a1567d954d583ee29c2b9700b627301afb28979339c6ad7157ca72d`](https://stellar.expert/explorer/testnet/tx/e44b97333a1567d954d583ee29c2b9700b627301afb28979339c6ad7157ca72d)  
- **Replay path:** [`agentos/docs/lab-stellar-testnet.md`](agentos/docs/lab-stellar-testnet.md) · `cd agentos && uv run python scripts/demo_stellar_api.py`

Fake remains available for offline CI. **The jury-facing network demo is Stellar Testnet**, not Fake.

---

## The problem we solve

Small and mid-sized businesses (starting with **cafés** and **clothing stores**) run on chat, cash, and trust. Generic chatbots invent prices, “confirm” payments in text, and can’t be audited. Banks and blockchains don’t speak WhatsApp. Owners need **hybrid workforce**: humans + agents — with a hard floor on money, stock, and accounting.

---

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
│  → transfer (Stellar Testnet) → ledger         │
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

## What was built when (honesty for the jury)

| Slice | Source | In this repo |
| --- | --- | --- |
| Factory commerce motor (WhatsApp, orders, cash, Baneco path, panel patterns) | Prior work (Agent-IA V2 lineage / Factory Agent OS) | Yes — under [`factory/`](factory/) |
| Factory platform phases (tenants, operator, canvas, roster, evals) | Factory Agent OS next, continued into this pack | Yes — [`factory/docs/00-vision-y-estado.md`](factory/docs/00-vision-y-estado.md) |
| AgentOS API, policy, ledger, Fake + Stellar adapters, SDK, MCP, Alembic, tests | **Hackathon window (≈ 2026-11-09 → 2026-11-22)** | Yes — under [`agentos/`](agentos/) |
| Monorepo review pack + Render free-tier Blueprint | 2026-11-22 | [`render.yaml`](render.yaml) |

Extraction strategy and exclusions: [`agentos/docs/`](agentos/docs/) (incl. ADR-001 extraction posture).

### Team (this submission)

| Person | Role in this build |
| --- | --- |
| **Diego Silvestre Borges Salces** | Architecture & implementation — AgentOS rails, Factory pack, Stellar lab, deploy Blueprint |
| **Adriana Torrico Uzqueda** | Product & business — narrative, UX direction, pilot/business validation with the café candidate (no application commits required for that work) |

---

## Start here (reviewers)

1. **Stellar evidence (above)** — open the stellar.expert links  
2. **Product narrative & honesty audit** → [`docs/pitch-deck-research.md`](docs/pitch-deck-research.md)  
3. **Factory vision & phase status** → [`factory/docs/00-vision-y-estado.md`](factory/docs/00-vision-y-estado.md)  
4. **AgentOS architecture & decisions** → [`agentos/docs/arquitectura.md`](agentos/docs/arquitectura.md) · [`agentos/docs/riesgos-y-decisiones.md`](agentos/docs/riesgos-y-decisiones.md)  
5. **Lab wiring Factory → AgentOS** → [`factory/docs/lab-production-like.md`](factory/docs/lab-production-like.md)

### Non-negotiables (read before demos)

- Tenant / organization identity comes from the **runtime**, never from model text  
- The LLM never receives database URLs, service roles, or raw SQL  
- Money, stock, orders, and journal entries keep a **human-approval floor**  
- Payment confirmation comes only from **adapters** — never from customer messages  

---

## Public demo

**Render Blueprint** for free-tier lab services is in [`render.yaml`](render.yaml) (`factory-agentos-*`, shared Postgres, **not** the live café `agent-ia-*` services).

**Public HTTPS URL:** pending first Blueprint apply — when live, it will be listed here as:

- Web (panel login, `AUTH_MODE=test`): `https://factory-agentos-web.onrender.com`  
- Factory API: `https://factory-agentos-api.onrender.com`  
- AgentOS rails: `https://factory-agentos-rails.onrender.com`  

Until then, reproduce locally (below) or replay Stellar via the published hash.

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
| Factory motor (WhatsApp, cobros, caja, catalog…) | Real-business context at a Santa Cruz café candidate; **live café deploy is out of scope for this lab pack** |
| Factory platform (tenants, operator, canvas, roster) | Phased delivery — see vision doc |
| AgentOS money path | Implemented; **Stellar Testnet payment evidenced above** |
| Mainnet / custody / full ramps | **Not** claimed — see readiness & roadmap in `agentos/docs/` |

This tree is a **lab and review build**. Do not point it at a live café database or production secrets.

---

## Atlaros

Built by **Atlaros** — Factory for the business conversation, AgentOS for the money rails, one brand for the hybrid workforce: **Factory AgentOS**.
