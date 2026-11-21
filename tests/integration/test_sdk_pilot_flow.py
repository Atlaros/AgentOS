from __future__ import annotations

import os
import uuid

import httpx
import pytest
from agentos_sdk import AgentOS
from agentos_sdk.client import AgentOSError

pytestmark = pytest.mark.skipif(
    os.getenv("AGENTOS_RUN_INTEGRATION") != "1",
    reason="Set AGENTOS_RUN_INTEGRATION=1 with API/Postgres",
)


def test_sdk_against_live_api_if_up() -> None:
    base = os.getenv("AGENTOS_BASE_URL", "http://127.0.0.1:8080")
    try:
        health = httpx.get(f"{base.rstrip('/')}/health", timeout=2.0)
    except httpx.HTTPError:
        pytest.skip("API not reachable")
    if health.status_code != 200:
        pytest.skip("API not healthy")

    token = os.getenv("AGENTOS_BOOTSTRAP_TOKEN", "change-me-lab-only")
    slug = f"live-{uuid.uuid4().hex[:8]}"
    boot = httpx.post(
        f"{base.rstrip('/')}/v1/bootstrap",
        json={
            "org_slug": slug,
            "org_name": "Live SDK",
            "app_name": "live",
            "owner_email": f"{slug}@example.com",
            "bootstrap_token": token,
        },
        timeout=30.0,
    )
    assert boot.status_code == 200, boot.text
    org_id = boot.json()["organization_id"]
    api_key = boot.json()["api_key"]

    with AgentOS(base_url=base, api_key=api_key, organization_id=org_id) as client:
        wallet = client.wallets.link(public_address="GFAKELIVE0001")
        payment = client.payments.create(
            from_wallet_id=wallet["id"],
            to_address="GFAKELIVEDEST1",
            amount="50",
            idempotency_key=f"live-pay-{uuid.uuid4().hex}",
        )
        assert payment["status"] == "pending_approval"
        with pytest.raises(AgentOSError) as blocked:
            client.transfers.execute(
                payment_request_id=payment["id"],
                idempotency_key=f"live-block-{uuid.uuid4().hex}",
            )
        assert blocked.value.status_code == 403
        client.payments.approve(payment["id"], reason="sdk live")
        transfer = client.transfers.execute(
            payment_request_id=payment["id"],
            idempotency_key=f"live-x-{uuid.uuid4().hex}",
        )
        assert transfer["status"] == "confirmed"
