#!/usr/bin/env python3
"""Stellar Testnet walkthrough via AgentOS REST API (not adapter-only).

Requires a running API started with the SAME lab secret:

  export AGENTOS_STELLAR_SECRET_KEY=S...
  uv run agentos-api

Then:

  uv run python scripts/demo_stellar_api.py
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import httpx
import requests
from stellar_sdk import Keypair

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "agentos_sdk"))

from agentos_sdk import AgentOS


def friendbot(address: str) -> None:
    response = requests.get(
        f"https://friendbot.stellar.org?addr={address}",
        timeout=60,
        headers={"User-Agent": "agentos-lab/0.1"},
    )
    # 400 "already funded" is fine for reruns of the same lab keypair.
    if response.status_code == 400 and "already funded" in response.text.lower():
        return
    response.raise_for_status()


def bootstrap(base_url: str, token: str) -> tuple[str, str]:
    slug = f"stellar-{uuid.uuid4().hex[:8]}"
    response = httpx.post(
        f"{base_url.rstrip('/')}/v1/bootstrap",
        json={
            "org_slug": slug,
            "org_name": "Stellar API Demo",
            "app_name": "stellar-demo",
            "owner_email": f"{slug}@example.com",
            "bootstrap_token": token,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["organization_id"], data["api_key"]


def main() -> int:
    secret = os.environ.get("AGENTOS_STELLAR_SECRET_KEY", "").strip()
    if not secret:
        print("Set AGENTOS_STELLAR_SECRET_KEY and restart the API with the same value.")
        return 1

    base_url = os.environ.get("AGENTOS_BASE_URL", "http://127.0.0.1:8080")
    token = os.environ.get("AGENTOS_BOOTSTRAP_TOKEN", "change-me-lab-only")

    source = Keypair.from_secret(secret)
    dest = Keypair.random()
    print("==> Friendbot source+dest")
    friendbot(source.public_key)
    friendbot(dest.public_key)

    org_id, api_key = bootstrap(base_url, token)
    print(f"organization_id={org_id}")

    with AgentOS(base_url=base_url, api_key=api_key, organization_id=org_id) as client:
        wallet = client.wallets.link(
            public_address=source.public_key,
            provider="stellar",
            network="testnet",
            label="lab-source",
        )
        print("==> Linked", wallet)
        print("==> Balances", client.wallets.balances(wallet["id"]))

        # amount 1 → auto-allow under default threshold 10
        payment = client.payments.create(
            from_wallet_id=wallet["id"],
            to_address=dest.public_key,
            amount="1",
            asset_code="XLM",
            memo="api-demo",
            idempotency_key=f"stellar-pay-{uuid.uuid4().hex[:8]}",
        )
        print("==> Payment", payment)
        assert payment["status"] == "approved", payment

        transfer = client.transfers.execute(
            payment_request_id=payment["id"],
            idempotency_key=f"stellar-x-{uuid.uuid4().hex[:8]}",
        )
        print("==> Transfer", transfer)
        assert transfer["status"] in {"confirmed", "submitted"}, transfer
        assert transfer.get("network_tx_id"), transfer
        print("==> Stellar API demo OK", transfer["network_tx_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
