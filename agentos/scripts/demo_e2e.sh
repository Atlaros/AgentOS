#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export AGENTOS_DATABASE_URL="${AGENTOS_DATABASE_URL:-postgresql+asyncpg://agentos:agentos@127.0.0.1:5433/agentos}"
export AGENTOS_BOOTSTRAP_TOKEN="${AGENTOS_BOOTSTRAP_TOKEN:-change-me-lab-only}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"

echo "==> Health"
curl -sf "$BASE_URL/health" | tee /tmp/agentos-health.json
echo

SLUG="demo-$(date +%s)"
echo "==> Bootstrap org=$SLUG"
BOOT="$(curl -sf -X POST "$BASE_URL/v1/bootstrap" \
  -H 'content-type: application/json' \
  -d "{\"org_slug\":\"$SLUG\",\"org_name\":\"Sunday Demo\",\"app_name\":\"demo-agent\",\"owner_email\":\"$SLUG@example.com\",\"bootstrap_token\":\"$AGENTOS_BOOTSTRAP_TOKEN\"}")"
echo "$BOOT" | tee /tmp/agentos-boot.json
ORG_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["organization_id"])' <<<"$BOOT")"
API_KEY="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["api_key"])' <<<"$BOOT")"

AUTH=(-H "Authorization: Bearer $API_KEY" -H "X-Organization-Id: $ORG_ID")

echo "==> Link fake wallet"
WALLET="$(curl -sf -X POST "$BASE_URL/v1/wallets/link" "${AUTH[@]}" \
  -H 'content-type: application/json' \
  -d '{"provider":"fake","network":"fake","public_address":"GFAKESOURCE0001","label":"lab"}')"
echo "$WALLET"
WALLET_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$WALLET")"

echo "==> Balances"
curl -sf "$BASE_URL/v1/wallets/$WALLET_ID/balances" "${AUTH[@]}"
echo

echo "==> Payment request (amount 50 → pending_approval)"
PAY="$(curl -sf -X POST "$BASE_URL/v1/payment-requests" "${AUTH[@]}" \
  -H 'content-type: application/json' -H 'Idempotency-Key: demo-pay-1' \
  -d "{\"from_wallet_id\":\"$WALLET_ID\",\"to_address\":\"GFAKEDEST0001\",\"amount\":\"50\",\"asset_code\":\"XLM\"}")"
echo "$PAY"
PAY_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$PAY")"

echo "==> Transfer without approve (expect 403)"
set +e
curl -s -o /tmp/agentos-blocked.json -w "%{http_code}" -X POST "$BASE_URL/v1/transfers" "${AUTH[@]}" \
  -H 'content-type: application/json' -H 'Idempotency-Key: demo-xfer-blocked' \
  -d "{\"payment_request_id\":\"$PAY_ID\"}" | tee /tmp/agentos-blocked.code
echo
set -e
test "$(cat /tmp/agentos-blocked.code)" = "403"

echo "==> Approve"
curl -sf -X POST "$BASE_URL/v1/payment-requests/$PAY_ID/approve" "${AUTH[@]}" \
  -H 'content-type: application/json' \
  -d '{"reason":"sunday demo"}'
echo

echo "==> Execute transfer"
XFER="$(curl -sf -X POST "$BASE_URL/v1/transfers" "${AUTH[@]}" \
  -H 'content-type: application/json' -H 'Idempotency-Key: demo-xfer-1' \
  -d "{\"payment_request_id\":\"$PAY_ID\"}")"
echo "$XFER"

echo "==> Ledger"
curl -sf "$BASE_URL/v1/ledger" "${AUTH[@]}"
echo
echo "==> Demo OK"
