#!/usr/bin/env python3
"""Phase 8 pilot: Agent-IA-shaped consumer of AgentOS (lives in AgentOS, no Agent-IA edits).

Simulates a café agent that:
1) bootstraps lab credentials (or reuses env),
2) links a Fake wallet,
3) requests a payment under policy,
4) gets human approval when required,
5) executes transfer and prints ledger proof.

Does NOT import Factory or Agent-IA code.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import httpx

# Allow running without install when launched via `uv run`
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "agentos_sdk"))

from agentos_sdk import AgentOS
from agentos_sdk.client import AgentOSError


def bootstrap(base_url: str, token: str) -> tuple[str, str]:
    slug = f"pilot-{uuid.uuid4().hex[:8]}"
    response = httpx.post(
        f"{base_url.rstrip('/')}/v1/bootstrap",
        json={
            "org_slug": slug,
            "org_name": "Agent-IA Pilot Café",
            "app_name": "agent-ia-pilot",
            "owner_email": f"{slug}@example.com",
            "bootstrap_token": token,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["organization_id"], data["api_key"]


def main() -> int:
    base_url = os.environ.get("AGENTOS_BASE_URL", "http://127.0.0.1:8080")
    token = os.environ.get("AGENTOS_BOOTSTRAP_TOKEN", "change-me-lab-only")

    org_id = os.environ.get("AGENTOS_ORGANIZATION_ID")
    api_key = os.environ.get("AGENTOS_API_KEY")
    if not org_id or not api_key:
        print("==> Bootstrap lab org for Agent-IA-shaped pilot")
        org_id, api_key = bootstrap(base_url, token)
        print(f"organization_id={org_id}")
        print("(api_key issued once — set AGENTOS_API_KEY to reuse)")

    with AgentOS(base_url=base_url, api_key=api_key, organization_id=org_id) as client:
        print("==> Org", client.orgs.me())

        print("==> Link Fake wallet (café till)")
        wallet = client.wallets.link(
            public_address="GFAKECAFE0001",
            provider="fake",
            network="fake",
            label="cafe-till",
        )
        wallet_id = wallet["id"]
        print(wallet)

        print("==> Balances", client.wallets.balances(wallet_id))

        print("==> Agent requests payout (amount 50 → require_human)")
        payment = client.payments.create(
            from_wallet_id=wallet_id,
            to_address="GFAKESUPPLIER01",
            amount="50",
            asset_code="XLM",
            memo="supplier-pay",
            idempotency_key=f"pilot-pay-{uuid.uuid4().hex[:8]}",
        )
        print(payment)
        assert payment["status"] == "pending_approval"

        print("==> Agent tries transfer without approval (expect 403)")
        try:
            client.transfers.execute(
                payment_request_id=payment["id"],
                idempotency_key=f"pilot-blocked-{uuid.uuid4().hex[:8]}",
            )
            print("ERROR: expected forbidden")
            return 1
        except AgentOSError as exc:
            assert exc.status_code == 403
            print(f"blocked_ok status={exc.status_code}")

        print("==> Human approves (café owner)")
        approved = client.payments.approve(payment["id"], reason="pilot ok")
        print(approved)

        print("==> Agent executes transfer")
        transfer = client.transfers.execute(
            payment_request_id=payment["id"],
            idempotency_key=f"pilot-xfer-{uuid.uuid4().hex[:8]}",
        )
        print(transfer)
        assert transfer["status"] == "confirmed"

        print("==> Ledger proof")
        for entry in client.ledger.list():
            print(f"  - {entry['entry_type']}: {entry['payload']}")

    print("==> Phase 8 pilot OK (Agent-IA-shaped client, no Agent-IA repo changes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
