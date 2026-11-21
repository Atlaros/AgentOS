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
async def test_client_credentials_token_and_api_key_still_work() -> None:
    from agentos_api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        slug = f"oauth-{uuid.uuid4().hex[:8]}"
        boot = await client.post(
            "/v1/bootstrap",
            json={
                "org_slug": slug,
                "org_name": "OAuth Org",
                "app_name": "oauth-app",
                "owner_email": f"{slug}@example.com",
                "bootstrap_token": os.getenv("AGENTOS_BOOTSTRAP_TOKEN", "change-me-lab-only"),
            },
        )
        assert boot.status_code == 200, boot.text
        org_id = boot.json()["organization_id"]
        app_id = boot.json()["application_id"]
        api_key = boot.json()["api_key"]

        bad = await client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": app_id,
                "client_secret": "not-the-key",
                "organization_id": org_id,
            },
        )
        assert bad.status_code == 401

        token_resp = await client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": app_id,
                "client_secret": api_key,
                "organization_id": org_id,
            },
        )
        assert token_resp.status_code == 200, token_resp.text
        body = token_resp.json()
        assert body["token_type"].lower() == "bearer"
        assert body["expires_in"] > 0
        access = body["access_token"]
        assert access.count(".") == 2

        me = await client.get(
            "/v1/organizations/me",
            headers={
                "Authorization": f"Bearer {access}",
                "X-Organization-Id": org_id,
            },
        )
        assert me.status_code == 200, me.text
        assert me.json()["id"] == org_id

        wrong_org = await client.get(
            "/v1/organizations/me",
            headers={
                "Authorization": f"Bearer {access}",
                "X-Organization-Id": str(uuid.uuid4()),
            },
        )
        assert wrong_org.status_code == 401

        still_key = await client.get(
            "/v1/organizations/me",
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Organization-Id": org_id,
            },
        )
        assert still_key.status_code == 200
