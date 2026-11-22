#!/usr/bin/env bash
# Reserved ngrok host. Points at this API on :8000.
# Meta callback (unchanged): https://ventilative-obsolete-mozell.ngrok-free.dev/webhooks/whatsapp
set -euo pipefail

DOMAIN="${NGROK_DOMAIN:-ventilative-obsolete-mozell.ngrok-free.dev}"
PORT="${API_PORT:-8000}"

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ngrok no está en PATH" >&2
  exit 1
fi

echo "Túnel https://${DOMAIN} → 127.0.0.1:${PORT}"
echo "Webhook Meta: https://${DOMAIN}/webhooks/whatsapp"
echo "Inbox:        https://${DOMAIN}/inbox"
echo "La API de Factory Agent OS tiene que estar en :${PORT}. No levantes otro proceso en ese puerto: es el mismo webhook."

exec ngrok http --url="${DOMAIN}" "${PORT}"
