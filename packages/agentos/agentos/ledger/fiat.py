"""Observed fiat payments from Factory. These rows do not move a wallet."""

from __future__ import annotations

import uuid

FIAT_ENTRY_TYPE = "fiat_settlement_observed"
FIAT_REF_TYPE = "fiat_settlement"


def settlement_id(organization_id: uuid.UUID, provider_ref: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"agentos:fiat:{organization_id}:{provider_ref}")


def replay_status(existing: dict[str, str] | None, payload: dict[str, str]) -> str:
    if existing is None:
        return "created"
    if existing != payload:
        return "conflict"
    return "replay"


def settlement_payload(
    *,
    provider: str,
    provider_ref: str,
    amount: str,
    currency: str,
) -> dict[str, str]:
    return {
        "provider": provider,
        "provider_ref": provider_ref,
        "amount": amount,
        "currency": currency,
        "source": "factory",
    }
