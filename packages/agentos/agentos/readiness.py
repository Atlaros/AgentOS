"""Lab seams for the six remaining post-MVP items.

Live billing charges, Baneco, mainnet, and custody storage stay closed.
"""

from __future__ import annotations

from typing import Any


class CustodyRefused(Exception):
    """Secret material must not be stored or signed from this process."""


_SECRET_MARKERS = ("secret", "private", "seed", "mnemonic")


def current_plan() -> dict[str, Any]:
    """The only plan this slice serves. Nothing is charged."""
    return {
        "code": "lab",
        "name": "Lab",
        "payment_provider": None,
        "charges": False,
    }


def connection_report(*, evm_rpc_url: str = "") -> list[dict[str, str]]:
    """Describe each seam without opening a network connection."""
    rpc = evm_rpc_url.strip()
    evm_status = "configured" if rpc else "not_connected"
    evm_detail = "rpc configured" if rpc else "evm_not_connected"
    return [
        {"name": "billing", "status": "ready", "detail": "lab plan, no payment provider"},
        {"name": "evm", "status": evm_status, "detail": evm_detail},
        {"name": "baneco", "status": "unverified", "detail": "baneco_api_unverified"},
        {"name": "mainnet", "status": "denied", "detail": "mainnet_denied"},
        {"name": "custody", "status": "refused", "detail": "secrets are not stored"},
        {"name": "console", "status": "ready", "detail": "GET /console"},
    ]


def refuse_secret(material: dict[str, Any]) -> None:
    """Reject key material before it can reach a table or an adapter."""
    for key in material:
        lowered = key.lower()
        if any(marker in lowered for marker in _SECRET_MARKERS):
            raise CustodyRefused("custody_refused")
