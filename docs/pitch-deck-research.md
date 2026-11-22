# Pitch deck research — Factory + AgentOS (Stellar hackathon)

**Audit date:** 2026-11-22  
**Scope (read-only):**  
- `factory/`  
- `agentos/`  
- Brief check of `Agent-IAv2 (sibling checkout)` (relationship only)  

**Method:** docs + source + seeds + contracts. No dependency install, no deploy, no secret values.  
**Cross-check:** Independent read-only audits reconciled into this file — [Factory audit](23f314a9-d4e2-45d6-babf-a89bd51de837), [AgentOS audit](46f1a22a-8ef1-4520-ba1b-c7e983d57ea7), [competitive research](32fbd83a-4219-4fca-9adf-c8000a5105f9).  
**Classification legend:** `IMPLEMENTADA` | `PARCIAL` | `SIMULADA` | `PLANIFICADA`

---

## 1. Resumen ejecutivo

Factory + AgentOS is a two-repo product story aimed at Bolivian entrepreneurs, SMEs, and larger businesses that already sell over WhatsApp and need technology without losing control of money.

| Layer | Product | Role |
| --- | --- | --- |
| Business | Owner, staff, customer | Human side of the hybrid workforce |
| Factory | Factory Agent OS | Digital employees, orders, catalog, caja, Baneco QR, visual flow map |
| AgentOS | AgentOS | Financial infrastructure for agents: policy, human approval, ledger, adapters |
| Network | Baneco (Factory) / Stellar Testnet or Fake (AgentOS) | Where money actually moves |

**What is credible for a Stellar jury today**

- Factory operates a real cafeteria pilot with Baneco QR, WhatsApp agents, and a growing multi-tenant Factory layer (provisioning, operator console, React Flow canvas with guardrails). Evidence: `Factory Agent OS/docs/00-vision-y-estado.md`, `docs/motor.md`, `db/seeds/catalog_cafe.json`.
- AgentOS implements the MVP money path: link wallet → payment request → policy → optional human approve → transfer → ledger, via REST, Python SDK, and MCP. Default lab path uses a **Fake** adapter; **Stellar Testnet XLM payments are real Horizon submits** when a lab signer env is set. Evidence: `AgentOS/README.md`, `packages/agentos/agentos/adapters/stellar.py`, `docs/lab-stellar-testnet.md`.
- Local Factory → AgentOS settlement wiring exists in lab docs and smoke scripts: adapter confirm posts fiat settlements; customer text does not. Evidence: `Factory Agent OS/docs/lab-production-like.md`.

**What must not be overstated**

- AgentOS mainnet, Baneco inside AgentOS, custody, USDC sends, Pollar ramps, and Trustless Work settlement are **not** complete product rails (`mainnet_denied`, `baneco_api_unverified`, Pollar/Trustless seams). Evidence: `packages/agentos/agentos/readiness.py`, `docs/roadmap.md`.
- Factory and AgentOS are **independent repos**. AgentOS does not import Factory. Live café deploy is explicitly out of bounds for lab work.
- “Fusion of Agent-IA V2 + Factory Agent” is the **product narrative**. Agent-IAv2 still exists as a separate repo; Factory Agent OS consolidates motor + Factory platform and syncs café content from Agent-IAv2. Evidence: `Agent-IAv2/README.md`, `Factory Agent OS/odd/tasks/sync-cafe-from-agent-iav2.md`.

**No invented commercial metrics.** This audit found no committed screenshots and no audited user/revenue counts in the repos.

---

## 2. Definición actual de Factory

**Factory Agent OS** is a platform for entrepreneurs, SMEs, and mid-size businesses to run a hybrid workforce: humans plus digital employees that attend, sell, and collect—starting with cafés and clothing shops. Evidence: `Factory Agent OS/README.md`, `docs/00-vision-y-estado.md`.

### Two layers, one product

| Layer | Meaning | Status (docs) |
| --- | --- | --- |
| **Motor (Business OS)** | WhatsApp, Adri, Cobros, Caja, catalog/stock, orders, suppliers, managerial accounting, analytics, reports, knowledge/media | Exists; operates a real business |
| **Factory (platform)** | Multi-business isolation, template provisioning, evals, operator console, process catalog, canvas with guardrails, owner autoservicio | Built in phases; several “primer corte” |

Evidence: `docs/00-vision-y-estado.md` (table “Dos capas, un producto”), `docs/adr/ADR-017-vision-y-alcance-factory-agent-os.md`.

### Relationship to Agent-IA V2 and “Factory Agent”

| Claim | Verified reading |
| --- | --- |
| Agent-IA V2 as operational predecessor | `Agent-IAv2/README.md`: digital employees for a MiPE; Closet via WhatsApp; references Factory Agent OS |
| Factory Agent as visual/config platform | ADR-017 “AI Agent Factory”: provisioning + discovery + canvas with barandas |
| Fusion | **PARCIAL**: work lands in Factory Agent OS (motor + Factory). Agent-IAv2 repo still present. Café sync task: `odd/tasks/sync-cafe-from-agent-iav2.md` |

### Architecture (general)

```text
Núcleo: negocios, usuarios, roles, auditoría, conversaciones, pedidos, pagos, runtime de agentes
Módulos: caja, proveedores, contabilidad, analítica, reportes, …
Plantillas: cafetería, ropa (datos)
Negocios: configuración por tenant
```

Evidence: `docs/00-vision-y-estado.md`, `docs/adr/ADR-017-…`.

Stack (verified): FastAPI + LangGraph agents + Postgres + Redis + Next.js 15 / React 19 / `@xyflow/react` + Model Gateway (Gemini → OpenRouter → Groq; `fake` in tests). Evidence: `pyproject.toml`, `apps/web/package.json`, `.env.example`, `docs/02-contratos.md`.

Guiding rule: **first understand, then improve, then automate.** Money, stock, orders, and journal entries have a human-approval floor the owner can raise, not lower. Evidence: `docs/00-vision-y-estado.md`.

---

## 3. Definición actual de AgentOS

**AgentOS** is open financial infrastructure for AI agents and businesses: independent of Factory Agent OS and Agent-IA V2. Agents live **outside** and consume REST / SDK / MCP.

**MVP heart:** link/query wallet → create payment request → pass policy (human approve when required) → execute transfer → read ledger.

Evidence: `AgentOS/README.md`, `docs/arquitectura.md`, `docs/README.md`.

### Domains (modular monolith)

| Domain | Responsibility | Evidence |
| --- | --- | --- |
| Identity & Access | Applications, API keys, agents, OAuth2 client-credentials | `packages/agentos/agentos/identity/`, `apps/api/agentos_api/oauth.py` |
| Organizations | Tenant isolation + RLS context | `docs/adr/ADR-003-multi-tenancy.md`, models |
| Wallets | Link external public addresses; no secret column | `ADR-004`, `routes.py` `/v1/wallets/link` |
| Ops | PaymentRequest, TransferIntent (use cases live in API routes; `packages/agentos/agentos/ops/` is empty) | `apps/api/agentos_api/routes.py` |
| Policy | allow / deny / require_human | `packages/agentos/agentos/policy/engine.py` |
| Ledger | Append-only audit | `packages/agentos/agentos/ledger/` |
| Adapters | Fake + Stellar Testnet (+ EVM read-only seam) | `adapters/fake.py`, `stellar.py`, `evm.py`, `registry.py` |

Invariant: tenant only from authenticated context; no private keys in product tables; adapter success is the only network confirmation source. Evidence: `AGENTS.md`, `docs/arquitectura.md`.

---

## 4. Arquitectura de las cuatro capas

```text
┌──────────────────────────────────────────────────────────┐
│ 1. NEGOCIO — dueño, equipo humano, cliente (WhatsApp)    │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│ 2. FACTORY — empleados digitales, pedidos, caja, cobros  │
│    Lienzo, plantillas, consola operador / dueño          │
└────────────────────────────┬─────────────────────────────┘
                             │ lab: AGENTOS_* → :8080
┌────────────────────────────▼─────────────────────────────┐
│ 3. AGENTOS — policy, aprobación humana, ledger, adapters │
│    REST · SDK · MCP                                      │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│ 4. RED — Baneco QR (Factory café) · Fake / Stellar       │
│    Testnet XLM (AgentOS) · mainnet DENIED in AgentOS     │
└──────────────────────────────────────────────────────────┘
```

Evidence: pitch framing validated against `docs/arquitectura.md` (Factory may consume AgentOS later; not the reverse), `Factory Agent OS/docs/lab-production-like.md` (ports 8000/3000 Factory, 8080/5433 AgentOS, Baneco stays in Factory path).

---

## 5. Stack tecnológico

Only technologies verified in manifests/config/docs. No secret values.

### Factory Agent OS

| Area | Technology | Evidence |
| --- | --- | --- |
| Frontend | Next.js 15.1, React 19, TypeScript, `@xyflow/react` 12 | `apps/web/package.json` |
| Backend | FastAPI, Uvicorn, Pydantic | `pyproject.toml` |
| Languages | Python ≥3.11, TypeScript | same |
| Agent runtime | LangGraph | `pyproject.toml` dependency `langgraph` |
| DB | PostgreSQL (host lab `:5434`), RLS runtime role | `.env.example`, `docs/lab-production-like.md` |
| Cache / queue | Redis | `.env.example` `REDIS_URL` |
| AI providers | Gemini primary; OpenRouter + Groq failover; Cohere embeddings optional; `MODEL_PROVIDER=fake` in pytest | `.env.example`, `docs/02-contratos.md`, `docs/motor.md` |
| Messaging | Meta WhatsApp (`WHATSAPP_OUTBOUND_PROVIDER=meta`) | `.env.example` |
| Payments | Baneco QR (`QR_PROVIDER=baneco`, webhook `/webhooks/payments/baneco`); Fake provider in tests | `.env.example`, `docs/02-contratos.md` |
| Auth (hosted) | Supabase hooks named in `.env.example`; local `AUTH_MODE=test` | `.env.example` |
| Observability | Langfuse optional (`OBSERVABILITY_PROVIDER=noop` default) | `.env.example` |
| Tests | pytest (+ evals), Vitest | `pyproject.toml`, `apps/web/package.json` |
| AgentOS bridge | Optional `AGENTOS_BASE_URL` / org / API key | `.env.example`, `docs/lab-production-like.md` |

### AgentOS

| Area | Technology | Evidence |
| --- | --- | --- |
| API | FastAPI app `apps/api` | `apps/api/` |
| Domain | Python package `agentos` (SQLAlchemy async, Alembic, Pydantic, bcrypt, PyJWT, httpx) | `packages/agentos/pyproject.toml` |
| Language | Python ≥3.12 | same |
| DB | PostgreSQL host `:5433` | `README.md`, `.env.example` |
| Blockchain | `stellar-sdk` ≥12,<14; Horizon Testnet default | `pyproject.toml`, `settings.py` |
| Surfaces | REST, MCP server (`apps/mcp`), thin SDK (`packages/agentos_sdk`) | README, `apps/mcp/agentos_mcp/server.py` |
| Lab UI | Static teller page `GET /console` | `readiness.py`, `console.html` |
| Out of MVP | LangGraph, Next.js, WhatsApp, commerce UI, billing charges | `README.md` “Out of scope”, `docs/arquitectura.md` |

### Blockchain / Web3 (AgentOS)

| Item | Status | Evidence |
| --- | --- | --- |
| Stellar Testnet Horizon | Default URL in settings | `settings.py` |
| Friendbot funding (lab runbook) | Documented | `docs/lab-stellar-testnet.md` |
| Mainnet | Denied by registry | `adapters/registry.py` |
| EVM | Optional balance read if RPC set; submit refused | `adapters/evm.py`, `readiness.py` |
| Pollar / Trustless Work | Credential seams only; not core settlement path | `.env.example`, `readiness.py`, `roadmap.md` |

---

## 6. Funcionalidades verificadas

### 6.1 Factory — product capabilities

| Capability | Class | Evidence |
| --- | --- | --- |
| WhatsApp customer sales agent (Adri) | IMPLEMENTADA (motor) | `docs/motor.md`, `employees.py` Sales/Adri tools |
| Cobros QR + payment status | IMPLEMENTADA (motor; Baneco or Fake) | `docs/02-contratos.md`, `.env.example` |
| Ops delivery after payment confirmed | IMPLEMENTADA (motor) | `docs/motor.md` agent table |
| Caja, suppliers, managerial ledger, analytics, reports | IMPLEMENTADA (motor) | `docs/motor.md` |
| Multi-tenant isolation (dedup, buffer, channel, modules as data) | IMPLEMENTADA (Factory phase 1) | `docs/00-vision-y-estado.md`, ADR-018 |
| Provision business from template | IMPLEMENTADA (phase 2) | ADR-019, `test_provision_business.py` |
| Evals per template | IMPLEMENTADA (phase 3) | ADR-020, `evals/` |
| Operator console | IMPLEMENTADA (phase 4) | `/operator`, ADR-021 |
| Process catalog / diagnosis | PARCIAL (primer corte) | ADR-022 |
| Flow canvas React Flow + typed ports + publish/try/propose | PARCIAL (primer corte product cut) | ADR-023/025, `/operator/flow`, `test_flow_canvas.py` |
| Owner autoservicio / signup | PARCIAL (off by default) | ADR-024, `/signup`, `/owner`, `PUBLIC_SIGNUP_ENABLED` |
| Tenant employee roster + clones | IMPLEMENTADA (lab) | ADR-026, `employees.py` |
| Factory → AgentOS fiat settlement on adapter confirm | PARCIAL (lab wiring) | `docs/lab-production-like.md`, `tests/test_agentos_settlement.py` |
| Async worker / job queue | PLANIFICADA | `workers/factory_os/worker/main.py` idle; `docs/motor.md` notes no worker |
| Full ERP / official financial statements | PLANIFICADA / explicit non-goal | ADR-017 “Qué no es” |
| Free-form Make-like programming canvas | PLANIFICADA / rejected | ADR-017 out of scope |
| Doc drift (motor vs vision) | — | `docs/motor.md` may still mark published flow map as missing while `00-vision` + tests treat it as done — prefer vision + tests for pitch |

### 6.2 Agent types (Factory)

From `packages/contracts/factory_os/contracts/employees.py` (`CONCEPTUAL_ROLES` / `EMPLOYEE_REGISTRY`):

| Role | Name | Customer WhatsApp | Notes |
| --- | --- | --- | --- |
| Orchestrator | Coordinador | routing | Does not execute business tools |
| Sales | Adri | yes | No charge / no catalog edit |
| Collections | Cobros | yes | `payment.create_qr`, `payment.status` |
| Ops | Operaciones | yes | Profile + delivery after pay |
| Postventa | Postventa | yes | Incidents / handoff |
| Inventory, Catalog, Accounting, Analyst, Suppliers | internal | no customer WA | Role-scoped tools |

### 6.3 AgentOS — financial capabilities

| Capability | Class | Evidence |
| --- | --- | --- |
| Bootstrap org + API key | IMPLEMENTADA | `POST /v1/bootstrap` in `routes.py` |
| OAuth2 client-credentials JWT | IMPLEMENTADA | `oauth.py`, unit/integration tests present |
| Link external wallet (fake or stellar/testnet) | IMPLEMENTADA | `POST /v1/wallets/link`; mainnet rejected |
| Balances via adapter | IMPLEMENTADA | Fake deterministic; Stellar Horizon account balances |
| Create payment request | IMPLEMENTADA | `POST /v1/payment-requests` |
| Policy allow / require_human / deny | IMPLEMENTADA | `policy/engine.py`; default auto-allow ≤ `AGENTOS_AUTO_ALLOW_AMOUNT_MAX` (example 10) |
| Human approve / reject (REST + SDK) | IMPLEMENTADA | `/approve`, `/reject`; SDK methods exist |
| Human approve via MCP tools | PARCIAL | MCP exposes 7 tools (wallets/payments/transfers/ledger); **no** approve/reject tools — use REST/SDK for the human gate |
| Execute transfer + idempotency | IMPLEMENTADA | `POST /v1/transfers` |
| Ledger list | IMPLEMENTADA | `GET /v1/ledger` |
| Fiat settlement ingest (from Factory confirm) | PARCIAL | `POST /v1/fiat-settlements` appends ledger observation only; does not move a wallet |
| Create org outside bootstrap | PLANIFICADA | Contract mentions `POST /v1/organizations`; runtime uses `POST /v1/bootstrap` |
| REST surface | IMPLEMENTADA | `routes.py` (+ oauth, readiness, rails) |
| Python SDK | IMPLEMENTADA | `packages/agentos_sdk` |
| MCP server tools | IMPLEMENTADA (subset) | `apps/mcp/agentos_mcp/server.py` |
| MCP client (consume external MCP) | IMPLEMENTADA (no policy/ledger) | `apps/mcp/.../client.py`, contratos |
| Fake network adapter | SIMULADA (intentional default demo) | `adapters/fake.py`, README |
| Stellar Testnet XLM payment | IMPLEMENTADA (real Horizon when signer set) | `stellar.py` `server.submit_transaction` |
| Stellar USDC send | PLANIFICADA / blocked | `asset_code != "XLM"` → failed |
| Mainnet | DENIED | `registry.py` `mainnet_denied` |
| Baneco inside AgentOS | PLANIFICADA / closed | `baneco_api_unverified` |
| Custody / secret storage | REFUSED | `CustodyRefused`, readiness |
| Billing charges | SIMULADA lab plan | `current_plan()` charges false |
| Console teller page | PARCIAL lab UI | `GET /console` |

---

## 7. Estado de Stellar

| Question | Answer | Evidence |
| --- | --- | --- |
| Integration exists? | **Yes**, `StellarTestnetAdapter` using `stellar-sdk` + Horizon | `adapters/stellar.py` |
| Real network or simulation? | **Real Testnet** when `AGENTOS_STELLAR_SECRET_KEY` is set; otherwise submit fails. **Fake** remains default Sunday demo | README, lab runbook, `submit_payment` |
| Operations on Testnet | Read balances (native + issued assets listed); **submit native XLM payment** only; memo ≤28 chars; idempotency cache in-process | `stellar.py` |
| Wallets / tools | External public key linked in DB; lab signer secret **only in env**, never DB; Friendbot for funding; Horizon Testnet URL | lab runbook, ADR-004 |
| Mainnet | Explicitly denied | `registry.py`, readiness `mainnet_denied` |
| What’s missing for “complete” financial ops | USDC path, custody/KMS, multi-signer production custody, Baneco↔Stellar bridge, Pollar ramps, Trustless Work escrow connected to execute path, mainnet policy | `roadmap.md` post-MVP |
| Predicted Mainnet | Named as future; currently hard-denied | readiness, roadmap |

**Honesty line for the jury:** Stellar is a working Testnet stretch for XLM transfers under AgentOS policy—not a production mainnet rail and not the café’s Baneco QR path.

Prior lab note (not re-run in this audit): a 1 XLM Testnet payment was confirmed through the local API after Friendbot funding (session memory 2026-11-21). Treat as historical lab evidence, not a live claim for the stage unless re-demonstrated.

---

## 8. Caso de uso de cafetería

### Catalog

| Fact | Value | Evidence |
| --- | --- | --- |
| Seed file | `Factory Agent OS/db/seeds/catalog_cafe.json` | path |
| Currency | BOB | seed `currency_note`, product `currency` |
| Product count in seed array | **53** | counted from JSON |
| SKU range note | c001–c054; **c048 missing** from array | scripted count |
| Docs claim | “54 productos” | `docs/motor.md` — **needs confirmation** vs seed |
| Shop knowledge | `db/seeds/shop_cafe.json` | profile/FAQs/voice |
| Default seed switch | `CATALOG_SEED=cafe` | `.env.example` |

### Orders, agents, payments

| Topic | Status | Notes |
| --- | --- | --- |
| Automated attention | IMPLEMENTADA | Adri + orchestrator on WhatsApp (motor) |
| Orders | IMPLEMENTADA | `origin` agent or counter |
| Payment methods | Baneco QR + cash (owner); Fake in tests | contracts + `.env.example` |
| QR Baneco | IMPLEMENTADA for pilot when credentials + `ENABLE_LIVE_PAYMENTS` | webhook Baneco; **do not claim AgentOS Baneco** |
| Live café | Documented as real operating business; lab must not touch its remote DB/deploy | `lab-production-like.md` prohibitions |
| Demo-safe path | Local Factory lab (`:8000`/`:3000`) + Fake payments **or** carefully scoped pilot UI without mutating live café | lab docs |

### Clothing template (Closet)

| Fact | Value | Evidence |
| --- | --- | --- |
| Seed | `db/seeds/catalog_closet.json` | 129 products, BOB |
| Role | Template / pytest fixture; Authentic Closet heritage | `docs/motor.md`, `.env.example` comments |
| Live second tenant | Not claimed as live production | ADR-017 phase gates |

---

## 9. Guion de demo de tres minutos

**Goal:** show four layers without claiming unfinished rails.  
**Prep (before stage):** Factory lab up; AgentOS up on `:8080` with Fake **and** optional Stellar Testnet signer funded; browser windows ready; **do not** use live café production DB.

| Time | Action | Screen / command | Says |
| --- | --- | --- | --- |
| 0:00–0:25 | Present business | `/operator` → Negocios (café tenant) | “This is a Bolivian café on Factory.” |
| 0:25–0:50 | Agents | Operator Empleados **or** contracts slide | “Adri sells; Cobros charges; Ops ships only after pay.” |
| 0:50–1:20 | Canvas | `/operator/flow?tenant_id=…` | “Flows use typed nodes—not free code.” Try/Publish if already published. |
| 1:20–1:50 | Order | Owner desk `/owner` manual order **or** lab WhatsApp inbox / Fake chat | Create a small order; avoid live Meta if unstable. |
| 1:50–2:15 | Payment request | Factory Cobros QR (Fake QR in lab) **or** jump to AgentOS | “Money cannot be confirmed by chat text.” |
| 2:15–2:40 | AgentOS policy | AgentOS: create payment amount **> auto_allow** → `pending_approval` → approve → transfer on **Fake** | “Policy + human gate + ledger.” Show `GET /v1/ledger`. |
| 2:40–3:00 | Stellar that works | Pre-run or live `scripts/demo_stellar_api.py` / Horizon tx hash for **1 XLM Testnet** | “Same policy path; adapter confirms on Stellar Testnet. Mainnet denied.” |

**Fallback if Stellar signer missing:** show Fake transfer + readiness report `stellar: ready (testnet_xlm)` + code path in `stellar.py`, and say Testnet was verified in lab—not on this machine.

**Do not demo:** AgentOS Baneco, mainnet, Pollar empty routes, Trustless as settled escrow, invented metrics.

---

## 10. Diferenciación competitiva

Sources for peers (external, verified in research pass):

- Coinbase AgentKit: https://docs.cdp.coinbase.com/agent-kit/welcome — wallet + onchain actions (EVM/Solana); LangChain/MCP/etc. **Does not** default to human approval / spend caps / destination allowlists ([Managing Risk](https://github.com/coinbase/agentkit)).
- Circle Agent Stack: https://developers.circle.com/agent-stack — Agent Wallets with spend policies, x402 nanopayments, Circle CLI ([intro blog](https://www.circle.com/blog/introducing-circle-agent-stack-financial-infrastructure-for-the-agentic-economy)).
- Builders / automation: Relevance, Voiceflow, Copilot Studio, Zapier AI, Make AI Agents — conversational UX and SaaS connectors; approvals are per-tool/workflow, not a financial ledger.
- Other money layers: Sequence Agentic, AgentRail, Stripe Agent Toolkit / Issuing — banking/card/metering rails for agents.

| Peer class | What they optimize | Factory + AgentOS (evidence-based difference) |
| --- | --- | --- |
| Traditional agent builders | Chat agents / tools | Factory is a **business OS** (orders, stock, caja, accounting) with role-scoped employees—not only a prompt+tools kit (`docs/motor.md`) |
| Automation platforms (Make/Zapier-like) | Generic connectors | Factory canvas has **typed ports and locked money path**; payment confirmed only by adapter (`ADR-017`) |
| Financial agent toolkits (AgentKit) | Onchain actions for builders | AgentOS adds **org tenancy, payment requests, policy, human approval before network, ledger**; Stellar Testnet stretch, not EVM-first AgentKit. AgentKit leaves guardrails to the developer by default |
| Circle Agent Stack | USDC agent wallets + spending policies / x402 | Overlap on **policy around spend**; Factory+AgentOS also ships **SME WhatsApp commerce + Baneco fiat QR** in Factory. Circle is stronger on USDC/x402; we do **not** claim feature parity |
| Bank/card agent rails | Payouts, virtual cards, metering | Different rail; AgentOS is a **control plane** (PaymentRequest → policy → adapter → ledger), not Issuing/Plaid |
| Generic “AI for SMEs” | Chatbots | Explicit non-goals: not a lone chatbot, not full ERP, not official statements (`ADR-017`) |

**Stellar angle for the jury:** peers above center on EVM + USDC or US bank rails. AgentOS’s documented first real network is **Stellar Testnet** with adapter-verified confirmation—credible if scoped honestly (XLM testnet, no mainnet custody).

**Current vs vision**

| Current (audited) | Vision (do not sell as done) |
| --- | --- |
| Café + Closet templates; Factory phases 1–4 strong; canvas primer corte | Many verticals, full autoservicio |
| AgentOS Fake + Stellar Testnet XLM + fiat settlement ledger ingest | Mainnet, Baneco-in-AgentOS, custody, USDC, ramps |
| Lab Factory↔AgentOS cable | Production unified money path |

Do **not** assert superiority without bake-off metrics—none were found in-repo.

---

## 11. Estado actual y roadmap

### Evidence of maturity

| Signal | Finding |
| --- | --- |
| Automated tests (Factory) | ≥119 `tests/test_*.py` files under `Factory Agent OS/tests` (+ `evals/`, Vitest in web) |
| Automated tests (AgentOS) | 11 unit + 5 integration modules under `AgentOS/tests` |
| Suite results this audit | **Not re-run** (no install/deploy per brief). Prior lab notes: AgentOS integration suite previously green (e.g. post-MVP readiness session). Re-run before jury day. |
| Screenshots in repos | **None** found under `docs/` image assets in this audit |
| Deployed usage metrics | **Not found** in repos (do not invent) |
| Live café | Documented as operating; treat as sensitive; lab docs forbid touching it from AgentOS/Factory lab scripts |

### Known limitations / risks

- Two codebases; production empalme Factory↔AgentOS is lab-grade.
- Stellar path lab-signer = single env key; not production custody.
- GitHub Actions billing lock on Atlaros noted historically for AgentOS CI.
- Canvas / autoservicio still “primer corte”.
- Café product count docs vs seed mismatch (54 vs 53 / missing c048).
- Pollar routes / Trustless not part of core confirmed demo.

### Priority next steps (from roadmaps, not invented)

1. Rehearse 3-minute demo on lab stack; capture Horizon tx hash + ledger screenshots.  
2. Keep Stellar Testnet XLM as the honest chain story; keep Baneco in Factory story.  
3. AgentOS post-MVP: only open rails that are verified (avoid claiming Pollar/Trustless until execute path works).  
4. Resolve café catalog count messaging.  
5. Production-hardening of Factory↔AgentOS settlement beyond lab.

---

## 12. Equipo fundador

Provided by founders for the pitch (not derived from git):

| Person | Role |
| --- | --- |
| **Diego Silvestre Borges Salces** | Co-founder, CTO / Technical Lead — architecture, development, AI/agents, infrastructure, integrations |
| **Adriana Torrico Uzqueda** | Co-founder, Product & Business Lead — product design, UI/UX, UX, commercial strategy, business validation |

---

## 13. Información que todavía necesitamos confirmar

1. **Live demo environment for jury day:** which host shows Factory UI without touching the production café?  
2. **Will Stellar Testnet signer be available on the demo machine** (Friendbot-funded) or only Fake + recorded tx?  
3. **Café product count** for slides: 53 (seed) vs 54 (docs) — pick one after fixing seed or docs.  
4. **Public company/product name** and logo lockup for slide 1.  
5. **Ask to the jury** (pilot, grant, mentorship)—not present in repos.  
6. **Any non-repo commercial traction** (active WhatsApp conversations, GMV)—only include if founders supply verifiable figures.  
7. **Whether Agent-IAv2 remains a public dependency narrative** or is fully retired in messaging (repo still exists).  
8. **Screenshot pack:** none in git; founders should export operator, flow, AgentOS ledger, Horizon tx.  
9. **Re-run** `uv run pytest` / Factory pytest on jury machines and paste pass counts into the deck appendix.  
10. **Competitive slide review** against latest Coinbase/Circle docs the week of the event (APIs change).  
11. **Demo path for human approval:** REST or SDK (MCP cannot approve today).  
12. **Whether to fix `docs/motor.md` drift** before linking jurors to Factory docs.

---

## Appendix A — Key file index

| Topic | Path |
| --- | --- |
| Factory vision | `Factory Agent OS/docs/00-vision-y-estado.md` |
| Factory scope ADR | `Factory Agent OS/docs/adr/ADR-017-vision-y-alcance-factory-agent-os.md` |
| Motor modules | `Factory Agent OS/docs/motor.md` |
| Contracts / Baneco | `Factory Agent OS/docs/02-contratos.md` |
| Lab Factory↔AgentOS | `Factory Agent OS/docs/lab-production-like.md` |
| Café seed | `Factory Agent OS/db/seeds/catalog_cafe.json` |
| Closet seed | `Factory Agent OS/db/seeds/catalog_closet.json` |
| Employee roles | `Factory Agent OS/packages/contracts/factory_os/contracts/employees.py` |
| AgentOS README | `AgentOS/README.md` |
| AgentOS architecture | `AgentOS/docs/arquitectura.md` |
| Stellar lab | `AgentOS/docs/lab-stellar-testnet.md` |
| Stellar adapter | `AgentOS/packages/agentos/agentos/adapters/stellar.py` |
| Adapter registry | `AgentOS/packages/agentos/agentos/adapters/registry.py` |
| Policy | `AgentOS/packages/agentos/agentos/policy/engine.py` |
| Readiness seams | `AgentOS/packages/agentos/agentos/readiness.py` |
| REST/MCP contracts | `AgentOS/docs/contratos-rest-mcp.md` |
| Roadmap | `AgentOS/docs/roadmap.md` |

---

## Appendix B — Suggested slide map (from this research)

1. Title + founders  
2. Problem (WhatsApp business, no safe automation)  
3. Four layers diagram  
4. Factory (motor + canvas)  
5. AgentOS (policy → approval → ledger)  
6. Stellar Testnet honesty slide  
7. Café case (53/54 BOB SKUs, Baneco in Factory)  
8. 3-minute demo promise  
9. Competitive frame (current vs vision)  
10. Ask + team  

---

*End of research audit. Classifications reflect repository evidence as of 2026-11-22. Re-verify demos and test counts before the Stellar jury presentation.*
