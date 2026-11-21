from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.skipif(
    os.getenv("AGENTOS_RUN_INTEGRATION") != "1",
    reason="Set AGENTOS_RUN_INTEGRATION=1 with Postgres on 5433",
)


@pytest.mark.asyncio
async def test_reject_application_and_agent_crud() -> None:
    from agentos_api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        slug = f"adm-{uuid.uuid4().hex[:8]}"
        boot = await client.post(
            "/v1/bootstrap",
            json={
                "org_slug": slug,
                "org_name": "Admin Org",
                "app_name": "root-app",
                "owner_email": f"{slug}@example.com",
                "bootstrap_token": os.getenv("AGENTOS_BOOTSTRAP_TOKEN", "change-me-lab-only"),
            },
        )
        assert boot.status_code == 200, boot.text
        org_id = boot.json()["organization_id"]
        api_key = boot.json()["api_key"]
        root_app_id = boot.json()["application_id"]
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Organization-Id": org_id,
        }

        app_resp = await client.post(
            "/v1/applications",
            headers=headers,
            json={"name": "secondary-app"},
        )
        assert app_resp.status_code == 201, app_resp.text
        assert app_resp.json()["api_key"].startswith("aos_")

        agent = await client.post(
            "/v1/agents",
            headers=headers,
            json={"name": "cafe-agent", "application_id": root_app_id},
        )
        assert agent.status_code == 201, agent.text
        agent_id = agent.json()["id"]

        listed = await client.get("/v1/agents", headers=headers)
        assert listed.status_code == 200
        assert any(a["id"] == agent_id for a in listed.json())

        got = await client.get(f"/v1/agents/{agent_id}", headers=headers)
        assert got.status_code == 200
        assert got.json()["name"] == "cafe-agent"

        wallet = await client.post(
            "/v1/wallets/link",
            headers=headers,
            json={
                "provider": "fake",
                "network": "fake",
                "public_address": "GFAKEADM0001",
                "label": "adm",
            },
        )
        assert wallet.status_code == 200
        wallet_id = wallet.json()["id"]

        payment = await client.post(
            "/v1/payment-requests",
            headers={**headers, "Idempotency-Key": f"rej-{uuid.uuid4().hex}"},
            json={
                "from_wallet_id": wallet_id,
                "to_address": "GFAKEDESTADM1",
                "amount": "50",
                "asset_code": "XLM",
            },
        )
        assert payment.status_code == 201
        assert payment.json()["status"] == "pending_approval"
        payment_id = payment.json()["id"]

        rejected = await client.post(
            f"/v1/payment-requests/{payment_id}/reject",
            headers=headers,
            json={"reason": "nope"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "rejected"

        blocked = await client.post(
            "/v1/transfers",
            headers={**headers, "Idempotency-Key": f"xfer-rej-{uuid.uuid4().hex}"},
            json={"payment_request_id": payment_id},
        )
        assert blocked.status_code == 403
