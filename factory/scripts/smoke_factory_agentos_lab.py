#!/usr/bin/env python3
"""Lab smoke: Factory adapter confirm → AgentOS fiat settlement.

Never points at the live café. Requires a local AgentOS on :8080.
Prints statuses only — never prints API keys.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT / "packages" / "domain"))
    sys.path.insert(0, str(ROOT / "packages" / "agents"))
    sys.path.insert(0, str(ROOT / "packages" / "tools"))
    sys.path.insert(0, str(ROOT / "packages" / "contracts"))
    sys.path.insert(0, str(ROOT / "packages" / "harness"))


def _bootstrap(base: str, token: str) -> tuple[str, str]:
    slug = f"factory-lab-{uuid.uuid4().hex[:8]}"
    response = httpx.post(
        f"{base.rstrip('/')}/v1/bootstrap",
        json={
            "org_slug": slug,
            "org_name": "Factory Lab Smoke",
            "app_name": "factory-smoke",
            "owner_email": f"{slug}@example.com",
            "bootstrap_token": token,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    body = response.json()
    return body["api_key"], body["organization_id"]


def main() -> int:
    base = (os.environ.get("AGENTOS_BASE_URL") or "http://127.0.0.1:8080").rstrip("/")
    token = (os.environ.get("AGENTOS_BOOTSTRAP_TOKEN") or "").strip()
    if not token:
        print("missing AGENTOS_BOOTSTRAP_TOKEN", file=sys.stderr)
        return 2

    health = httpx.get(f"{base}/health", timeout=10.0)
    health.raise_for_status()
    print("agentos_health", health.status_code)

    api_key, org_id = _bootstrap(base, token)
    os.environ["AGENTOS_BASE_URL"] = base
    os.environ["AGENTOS_API_KEY"] = api_key
    os.environ["AGENTOS_ORGANIZATION_ID"] = org_id
    print("bootstrapped_org", org_id)

    from factory_os.agents.turn import ShopRuntime
    from factory_os.domain.models import PILOT_TENANT_ID, PaymentStatus
    from factory_os.domain.seed import catalog_seed_path, load_catalog_json
    from factory_os.domain.store import MemoryCommerceStore
    from factory_os.tools.agentos_settlement import notifier_from_env
    from factory_os.tools.registry import FakePaymentProvider

    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(catalog_seed_path("cafe"), store)
    posts: list[str] = []
    live = notifier_from_env()
    assert live is not None

    def counting(payment):
        posts.append(payment.provider_ref)
        live(payment)

    shop = ShopRuntime(store, FakePaymentProvider(), settlement_notifier=counting)
    wa = f"5917{uuid.uuid4().hex[:7]}"
    shop.handle_turn(PILOT_TENANT_ID, wa, "quiero empanadas")
    shop.handle_turn(PILOT_TENANT_ID, wa, "confirmo")
    conv = store.list_conversations(PILOT_TENANT_ID)[0]
    ref = conv.state.provider_ref
    assert ref, "expected provider_ref after confirmo"

    shop.handle_turn(PILOT_TENANT_ID, wa, "ya pagué")
    payment = store.payment_status(PILOT_TENANT_ID, ref)
    assert payment is not None and payment.status is PaymentStatus.PENDING
    assert posts == [], "customer text must not post to AgentOS"
    print("customer_text_no_settlement", "ok")

    shop.confirm_payment_from_adapter(ref)
    payment = store.payment_status(PILOT_TENANT_ID, ref)
    assert payment is not None and payment.status is PaymentStatus.CONFIRMED
    assert posts == [ref], f"adapter confirm must post once, got {posts}"
    print("adapter_confirm_settlement", "ok", ref)

    from factory_os.tools.agentos_settlement import settlement_request

    replay_req = settlement_request(
        payment,
        base_url=base,
        api_key=api_key,
        organization_id=org_id,
    )
    replay = httpx.request(
        replay_req["method"],
        replay_req["url"],
        headers=replay_req["headers"],
        json=replay_req["json"],
        timeout=10.0,
    )
    print("idempotent_replay", replay.status_code)
    if replay.status_code not in {200, 201}:
        print("replay_body", replay.text[:200], file=sys.stderr)
        return 1
    print("lab_smoke_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
