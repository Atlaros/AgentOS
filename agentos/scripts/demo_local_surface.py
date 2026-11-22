"""Local prod-shaped smoke against a running AgentOS API.

Uses the same doors as production: bootstrap token, bearer, and
X-Organization-Id. Prints statuses only. Does not print keys.
"""

from __future__ import annotations

import os
import sys
import uuid

import httpx


def main() -> int:
    base = os.environ.get("AGENTOS_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    token = os.environ.get("AGENTOS_BOOTSTRAP_TOKEN", "change-me-lab-only")
    with httpx.Client(base_url=base, timeout=30.0) as http:
        health = http.get("/health")
        health.raise_for_status()
        print("health", health.status_code, health.json())

        closed = http.get("/v1/connections")
        print("connections_without_token", closed.status_code)
        if closed.status_code != 401:
            return 1

        fund = http.post("/v1/escrows/fund", json={"contract_id": "C", "signer": "G", "amount": "1"})
        print("escrow_fund", fund.status_code)
        if fund.status_code != 404:
            return 1

        slug = f"local-{uuid.uuid4().hex[:8]}"
        boot = http.post(
            "/v1/bootstrap",
            json={
                "org_slug": slug,
                "org_name": "Local Prod Smoke",
                "app_name": "local-smoke",
                "owner_email": f"{slug}@example.com",
                "bootstrap_token": token,
            },
        )
        boot.raise_for_status()
        body = boot.json()
        headers = {
            "Authorization": f"Bearer {body['api_key']}",
            "X-Organization-Id": body["organization_id"],
        }
        print("bootstrapped", body["organization_id"])

        connections = http.get("/v1/connections", headers=headers)
        connections.raise_for_status()
        report = {item["name"]: item["status"] for item in connections.json()}
        print("connections", report)
        if report.get("stellar") != "ready":
            return 1
        if report.get("mainnet") != "denied":
            return 1

        ramps = http.get("/v1/ramps/routes", headers=headers)
        print("ramps", ramps.status_code, ramps.json().get("detail", "ok"))
        pollar_key = os.environ.get("AGENTOS_POLLAR_API_KEY", "").startswith("sec_")
        if pollar_key and ramps.status_code != 200:
            return 1
        if not pollar_key and ramps.status_code != 503:
            return 1
    print("local surface OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
