from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

# Integration tests require Postgres (docker compose).
pytestmark = pytest.mark.skipif(
    os.getenv("AGENTOS_RUN_INTEGRATION") != "1",
    reason="Set AGENTOS_RUN_INTEGRATION=1 with Postgres on 5433",
)


@pytest.fixture
async def client():
    from agentos_api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_wallet_to_transfer_under_policy(client: AsyncClient) -> None:
    slug = f"demo-{uuid.uuid4().hex[:8]}"
    boot = await client.post(
        "/v1/bootstrap",
        json={
            "org_slug": slug,
            "org_name": "Demo Org",
            "app_name": "demo-app",
            "owner_email": f"{slug}@example.com",
            "bootstrap_token": os.getenv("AGENTOS_BOOTSTRAP_TOKEN", "change-me-lab-only"),
        },
    )
    assert boot.status_code == 200, boot.text
    data = boot.json()
    org_id = data["organization_id"]
    api_key = data["api_key"]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Organization-Id": org_id,
    }

    unauthorized = await client.get("/v1/organizations/me", headers={"X-Organization-Id": org_id})
    assert unauthorized.status_code == 401

    me = await client.get("/v1/organizations/me", headers=headers)
    assert me.status_code == 200

    linked = await client.post(
        "/v1/wallets/link",
        headers=headers,
        json={
            "provider": "fake",
            "network": "fake",
            "public_address": "GFAKESOURCE0001",
            "label": "lab-source",
        },
    )
    assert linked.status_code == 200, linked.text
    wallet_id = linked.json()["id"]

    balances = await client.get(f"/v1/wallets/{wallet_id}/balances", headers=headers)
    assert balances.status_code == 200
    assert float(balances.json()[0]["amount"]) == 1000.0

    # Small amount → auto-allow → approved
    small = await client.post(
        "/v1/payment-requests",
        headers={**headers, "Idempotency-Key": "pay-small-1"},
        json={
            "from_wallet_id": wallet_id,
            "to_address": "GFAKEDEST0001",
            "amount": "5",
            "asset_code": "XLM",
        },
    )
    assert small.status_code == 201, small.text
    assert small.json()["status"] == "approved"
    assert small.json()["policy_effect"] == "allow"

    transfer_small = await client.post(
        "/v1/transfers",
        headers={**headers, "Idempotency-Key": "xfer-small-1"},
        json={"payment_request_id": small.json()["id"]},
    )
    assert transfer_small.status_code == 200, transfer_small.text
    assert transfer_small.json()["status"] == "confirmed"

    # Large amount → require_human → must approve before transfer
    large = await client.post(
        "/v1/payment-requests",
        headers={**headers, "Idempotency-Key": "pay-large-1"},
        json={
            "from_wallet_id": wallet_id,
            "to_address": "GFAKEDEST0002",
            "amount": "50",
            "asset_code": "XLM",
        },
    )
    assert large.status_code == 201, large.text
    assert large.json()["status"] == "pending_approval"
    payment_id = large.json()["id"]

    blocked = await client.post(
        "/v1/transfers",
        headers={**headers, "Idempotency-Key": "xfer-large-blocked"},
        json={"payment_request_id": payment_id},
    )
    assert blocked.status_code == 403

    approved = await client.post(
        f"/v1/payment-requests/{payment_id}/approve",
        headers=headers,
        json={"reason": "lab ok"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    transfer_large = await client.post(
        "/v1/transfers",
        headers={**headers, "Idempotency-Key": "xfer-large-1"},
        json={"payment_request_id": payment_id},
    )
    assert transfer_large.status_code == 200, transfer_large.text
    assert transfer_large.json()["status"] == "confirmed"
    assert transfer_large.json()["network_tx_id"]

    ledger = await client.get("/v1/ledger", headers=headers)
    assert ledger.status_code == 200
    types = {e["entry_type"] for e in ledger.json()}
    assert "policy_decision" in types
    assert "transfer_confirmed" in types
