#!/usr/bin/env bash
# Daily Analítica owner digest (ADR-013 T3). Cron example (La Paz ~09:00):
#   0 9 * * * cd /path/to/factory-agent-os && ./scripts/run_analytics_digest.sh
# Requires OWNER_DASHBOARD_TOKEN and a running API. Opt-in must be enabled in Analítica.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/.env"
  set +a
fi
API_BASE="${API_BASE:-http://127.0.0.1:8000}"
TOKEN="${OWNER_DASHBOARD_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
  echo "OWNER_DASHBOARD_TOKEN missing" >&2
  exit 1
fi
curl -fsS -X POST "$API_BASE/api/analytics/digest/run" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
echo
