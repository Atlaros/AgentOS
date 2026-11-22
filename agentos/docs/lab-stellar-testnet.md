# Lab runbook — Stellar Testnet (stretch)

**Goal:** optional real XLM transfer on Testnet. Fake remains the default demo path.

## Safety

- Never put a secret key in Postgres or commit it.
- Set `AGENTOS_STELLAR_SECRET_KEY` only in local `.env` (gitignored).
- Mainnet (`public`) is denied by the registry.

## Setup

1. Create two Testnet keypairs (source + destination):

```bash
uv run python - <<'PY'
from stellar_sdk import Keypair
src = Keypair.random()
dst = Keypair.random()
print("SOURCE_PUBLIC=", src.public_key)
print("SOURCE_SECRET=", src.secret)
print("DEST_PUBLIC=", dst.public_key)
PY
```

2. Fund both with Friendbot (send a User-Agent; bare curl may get 403):

```bash
curl -A 'agentos-lab/0.1' "https://friendbot.stellar.org?addr=$SOURCE_PUBLIC"
curl -A 'agentos-lab/0.1' "https://friendbot.stellar.org?addr=$DEST_PUBLIC"
```


3. Put the **source** secret in `.env`:

```bash
AGENTOS_STELLAR_SECRET_KEY=S................................
AGENTOS_STELLAR_HORIZON_URL=https://horizon-testnet.stellar.org
```

4. Restart API, bootstrap (or reuse org), then:

```bash
# link the SOURCE public address
curl -X POST http://127.0.0.1:8080/v1/wallets/link \
  -H "Authorization: Bearer $API_KEY" \
  -H "X-Organization-Id: $ORG_ID" \
  -H 'content-type: application/json' \
  -d "{\"provider\":\"stellar\",\"network\":\"testnet\",\"public_address\":\"$SOURCE_PUBLIC\",\"label\":\"lab-source\"}"
```

5. Create payment request (amount ≤ 10 auto-allows; >10 needs approve) to `$DEST_PUBLIC`, then `POST /v1/transfers`.

The lab signer can **only** pay from the public key derived from `AGENTOS_STELLAR_SECRET_KEY`.

## API walkthrough (script)

With the API already running under the same `AGENTOS_STELLAR_SECRET_KEY`:

```bash
uv run python scripts/demo_stellar_api.py
```

This bootstraps an org, links the signer public key on `stellar/testnet`, creates an auto-allowed 1 XLM payment, and executes the transfer through REST/SDK.

## Verify

- Transfer status `confirmed` with a Horizon `network_tx_id` (tx hash).
- Ledger shows `transfer_confirmed`.
- No secret appears in ledger payloads.

