# AgentOS — coding invariants

1. Independent of Factory Agent OS and Agent-IA V2. No imports from those codebases.
2. Tenant (`organization_id`) only from authenticated context — never from free-form agent text.
3. No private keys / secrets in Postgres product tables.
4. Financial writes require typed request + scopes + policy + idempotency key.
5. Adapter success is the only source of on-chain / network confirmation.
6. Prefer Fake adapter in unit tests; integration may use Postgres on port **5433**.
7. Do not add LangGraph, WhatsApp, commerce catalog, or canvas modules.
