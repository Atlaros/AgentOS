# Post-MVP readiness

**Objective:** Leave the six remaining AgentOS post-MVP seams testable in the lab. Live Baneco, mainnet, custody, and a billing provider stay closed.  
**Branch:** `main` (no commit — user forbade commits and push)  
**Delivery:** ask-on-risk, local only. GitHub Actions stays parked.  
**Runner:** `uv run pytest -q` and `AGENTOS_RUN_INTEGRATION=1 uv run pytest -q`

## Specs

- **S1** Roadmap: "UI consola propia". Lab shell at `GET /console`. No Factory web app.
- **S2** Roadmap: "Billing / planes SaaS". Current plan is `lab`, `payment_provider` is null, no charge.
- **S3** Roadmap: "Otros adapters (EVM u otras chains)". Read-only Sepolia adapter. No RPC means `evm_not_connected`. `submit_payment` does not move funds.
- **S4** Roadmap: "Baneco / fiat, solo con API verificada". Status `unverified`. No HTTP client for Baneco.
- **S5** Roadmap: "Mainnet". Stays `mainnet_denied`. Existing registry behavior holds.
- **S6** Roadmap: "Custodia / KMS / HSM". Secret material is refused. Wallet rows gain no secret column.
- **S7** User: "dejando de lado git action por el momento". Do not edit the workflow. Do not commit or push.
- **A1** Assumption: EVM is not added to the payment execute path in this slice.
- **A2** Assumption: no live RPC, Baneco, mainnet, or HSM credentials are available.

## Tasks

| ID | Specs | Route | Status |
| --- | --- | --- | --- |
| T1 | S2 S4 S5 S6 | inline | done |
| T2 | S3 | inline | done |
| T3 | S1 S7 | inline | done |

## Log

- **L1** User asked to keep working the six remaining post-MVP items while away, with ODD and TDD, and to leave them ready to test and connect. Factory unification stays in Factory. GitHub Actions stays parked. No commit unless asked.
- **L2** 2026-11-21 RED: `tests/unit/test_post_mvp_readiness.py` collected `ModuleNotFoundError: agentos.adapters.evm`. GREEN: `AGENTOS_RUN_INTEGRATION=1 uv run pytest -q` → 34 passed. Ruff and mypy clean on the new modules. Console checked in the browser at `127.0.0.1:8091/console`; Connections without a token returns 401. Live Baneco, mainnet, custody, and a billing charge stay closed. Not committed. Risk: item 3 (`create_app` is shared; `/health` still returns ok).
