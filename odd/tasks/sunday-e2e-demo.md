# Sunday E2E demo — wallet → transfer under policy

**Objective:** Working demo by Sunday: link wallet → payment request → policy → (approve if needed) → Fake transfer → ledger.  
**Branch:** `main` (or `feat/sunday-e2e` if branching). Delivery: local demo script; no push/PR required unless owner asks.  
**Runner:** `uv run pytest` · demo: `./scripts/demo_e2e.sh`

## Specs

- **S1** Owner chose deliverable B: "llegar domingo con un demo end-to-end del corazón (wallet → transfer bajo policy)"
- **S2** Locked decisions: D1 Alt B · D3 hashed API keys · D4 signer env lab · D5 XLM native · D6 REST first (no MCP Sunday) · D7 multi-org membership · D8 docs in `docs/` · D9 Factory exclusions
- **S3** Primary network for Sunday demo: **Fake** (deterministic). Stellar Testnet = stretch only if time
- **S4** Heart path: auth with API key → link wallet → balances → create payment-request → policy allow or require_human → approve → execute transfer → confirmed + ledger entries
- **S5** No Factory / Agent-IA imports · no secrets in DB · no commerce/LangGraph/WhatsApp

## Tasks

| ID | Specs | Route | Status | Evidence |
| --- | --- | --- | --- | --- |
| T1 | S2 | inline | done | lock riesgos + this file |
| T2 | S5 | inline | done | scaffold uv/FastAPI/Postgres/Alembic/CI |
| T3 | S4 | inline | done | identity + orgs + API keys + RLS + bootstrap |
| T4 | S3 S4 | inline | done | wallets + Fake balances |
| T5 | S4 | inline | done | policy + payment requests + transfers + ledger |
| T6 | S1 S4 | inline | done | demo script + README + pytest 5 passed |

## Log

- **L1** User: "(B) llegar domingo con un demo end-to-end del corazón (wallet → transfer bajo policy)"
- **L2** Locked recommended D1–D9; MCP/Stellar deferred for Sunday; package layout collapsed to single `agentos` installable with domain modules (still modular monolith, no Factory).
- **L3** 2026-11-20: Fake E2E path implemented. `uv run pytest` → 5 passed (unit+integration). `scripts/demo_e2e.sh` walkthrough. API on :8080, Postgres :5433.
- **L4** 2026-11-20: Stellar Testnet adapter + registry (mainnet denied); wallets may link `stellar/testnet`; bootstrap seeds testnet XLM asset; lab runbook `docs/lab-stellar-testnet.md`. Signer only via `AGENTOS_STELLAR_SECRET_KEY`. Live Testnet payment confirmed via adapter; Friendbot needs User-Agent. pytest 10 passed.
- **L5** User asked to finish including Phase 8 today. Phase 8 delivered as Agent-IA-shaped client inside AgentOS (`examples/pilot_agent_ia_client.py`) — no Agent-IA/Factory repo edits (D9). Also Phase 7: `agentos-sdk` + `agentos-mcp` (tools → SDK → REST/policy).
- **L6** Small-debt batch: cross-org test; reject/apps/agents REST; Stellar API demo script; CI still blocked by GitHub billing lock on Atlaros (workflow port fixed to 5432 for GHA).
- **L7** 2026-11-21 verification: `AGENTOS_RUN_INTEGRATION=1 uv run pytest -q` → **16 passed**; `uv run ruff check packages apps tests examples scripts` → All checks passed; `scripts/demo_stellar_api.py` → Stellar Testnet transfer **confirmed** (hash `a557cd19…`); friendbot treats already-funded 400 as OK; `_format_amount` trims Numeric(36,18) scale. CI remote still billing-locked. No commit in this fork.
