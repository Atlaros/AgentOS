"""Tell the local AgentOS that an adapter confirmed a fiat payment.

The post records a ledger fact. It does not create a wallet transfer.
Customer text never reaches this module.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from factory_os.domain.models import Payment


def settlement_request(
    payment: Payment,
    *,
    base_url: str,
    api_key: str,
    organization_id: str,
) -> dict[str, Any]:
    return {
        "method": "POST",
        "url": f"{base_url.rstrip('/')}/v1/fiat-settlements",
        "headers": {
            "Authorization": f"Bearer {api_key}",
            "X-Organization-Id": organization_id,
            "Idempotency-Key": payment.provider_ref,
        },
        "json": {
            "provider": payment.provider,
            "provider_ref": payment.provider_ref,
            "amount": format(payment.amount, "f"),
            "currency": payment.currency,
        },
    }


def notifier_from_env():
    """Return a payment callback, or None when AgentOS is not configured."""
    base_url = (os.environ.get("AGENTOS_BASE_URL") or "").strip()
    api_key = (os.environ.get("AGENTOS_API_KEY") or "").strip()
    organization_id = (os.environ.get("AGENTOS_ORGANIZATION_ID") or "").strip()
    if not base_url or not api_key or not organization_id:
        return None

    def notify(payment: Payment) -> None:
        request = settlement_request(
            payment,
            base_url=base_url,
            api_key=api_key,
            organization_id=organization_id,
        )
        response = httpx.request(
            request["method"],
            request["url"],
            headers=request["headers"],
            json=request["json"],
            timeout=5.0,
        )
        response.raise_for_status()

    return notify
