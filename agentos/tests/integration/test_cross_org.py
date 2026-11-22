from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.skipif(
    os.getenv("AGENTOS_RUN_INTEGRATION") != "1",
    reason="Set AGENTOS_RUN_INTEGRATION=1 with Postgres on 5433",
)


async def _bootstrap(client: AsyncClient, slug: str) -> dict:
    boot = await client.post(
        "/v1/bootstrap",
        json={
            "org_slug": slug,
            "org_name": f"Org {slug}",
            "app_name": "app",
            "owner_email": f"{slug}@example.com",
            "bootstrap_token": os.getenv("AGENTOS_BOOTSTRAP_TOKEN", "change-me-lab-only"),
        },
    )
    assert boot.status_code == 200, boot.text
    return boot.json()


@pytest.mark.asyncio
async def test_cross_org_wallet_isolation() -> None:
    from agentos_api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        a = await _bootstrap(client, f"orga-{uuid.uuid4().hex[:8]}")
        b = await _bootstrap(client, f"orgb-{uuid.uuid4().hex[:8]}")

        headers_a = {
            "Authorization": f"Bearer {a['api_key']}",
            "X-Organization-Id": a["organization_id"],
        }
        headers_b = {
            "Authorization": f"Bearer {b['api_key']}",
            "X-Organization-Id": b["organization_id"],
        }

        linked = await client.post(
            "/v1/wallets/link",
            headers=headers_a,
            json={
                "provider": "fake",
                "network": "fake",
                "public_address": "GFAKEORGA0001",
                "label": "a-only",
            },
        )
        assert linked.status_code == 200, linked.text
        wallet_id = linked.json()["id"]

        # Org B must not see Org A's wallet
        stolen = await client.get(f"/v1/wallets/{wallet_id}/balances", headers=headers_b)
        assert stolen.status_code == 404

        listed_b = await client.get("/v1/wallets", headers=headers_b)
        assert listed_b.status_code == 200
        assert listed_b.json() == []

        # Wrong org header with Org A key → unauthorized
        mixed = await client.get(
            "/v1/wallets",
            headers={
                "Authorization": f"Bearer {a['api_key']}",
                "X-Organization-Id": b["organization_id"],
            },
        )
        assert mixed.status_code == 401
