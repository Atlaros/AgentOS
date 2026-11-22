# OAuth2 client-credentials

**Objective:** Applications exchange `client_id` + API key for a short-lived bearer token. Existing API keys keep working.  
**Branch:** `main`  
**Runner:** `AGENTOS_RUN_INTEGRATION=1 uv run pytest tests/integration/test_oauth_token.py tests/unit/test_oauth_tokens.py -q`

## Specs

- **S1** User: start post-MVP with OAuth2; API keys stay; use ODD + TDD.
- **S2** Grant: `client_credentials` only. `client_id` is the application UUID. `client_secret` is the raw API key (still stored hashed). `organization_id` is required on the token request so RLS can scope the lookup.
- **S3** `POST /oauth/token` returns `access_token`, `token_type=bearer`, `expires_in`.
- **S4** Bearer JWT works on an existing route with the same scopes. `X-Organization-Id` must match the token org.
- **S5** Bad secret → 401. Expired token → 401. API key bearer still works.
- **S6** No Factory/Agent-IA edits. No authorization-code UI. No secrets in DB.

## Tasks

| ID | Specs | Route | Status |
| --- | --- | --- | --- |
| T1 | S1-S6 | inline | done |

## Log

- **L1** User asked to start the post-MVP list at OAuth2 with Gentle AI ODD and TDD. Billing lock stays parked. Later items (MCP client, Agent-IA pilot repo, UI, billing, EVM, fiat, mainnet, custody) are out of this slice.
- **L2** 2026-11-21 RED: `tests/unit/test_oauth_tokens.py` collected `ModuleNotFoundError: agentos.identity.oauth`. GREEN: unit expiry + integration token/API-key. `AGENTOS_RUN_INTEGRATION=1 uv run pytest -q` → 17 passed, 1 skipped. `uv run ruff check packages apps tests` clean. `organization_id` on the token form is required because application rows are FORCE RLS and the token route has no session yet. Risk: item 2 (auth) and item 3 (new `/oauth/token` contract), both covered by the new tests. Not committed.
