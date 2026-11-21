from __future__ import annotations

import json
import os
from typing import Any

from agentos_sdk import AgentOS
from agentos_sdk.client import AgentOSError
from mcp.server.mcpserver import MCPServer

mcp = MCPServer(name="agentos", version="0.1.0")


def _client() -> AgentOS:
    base_url = os.environ.get("AGENTOS_BASE_URL", "http://127.0.0.1:8080")
    api_key = os.environ.get("AGENTOS_API_KEY", "")
    org_id = os.environ.get("AGENTOS_ORGANIZATION_ID", "")
    if not api_key or not org_id:
        raise RuntimeError(
            "Set AGENTOS_API_KEY and AGENTOS_ORGANIZATION_ID (MCP has no bypass path)"
        )
    return AgentOS(base_url=base_url, api_key=api_key, organization_id=org_id)


def _dump(data: Any) -> str:
    return json.dumps(data, default=str)


@mcp.tool()
def list_wallets() -> str:
    """List linked wallets for the authenticated organization."""
    with _client() as client:
        return _dump(client.wallets.list())


@mcp.tool()
def get_balances(wallet_id: str) -> str:
    """Get balances for a linked wallet via the network adapter."""
    with _client() as client:
        return _dump(client.wallets.balances(wallet_id))


@mcp.tool()
def create_payment_request(
    from_wallet_id: str,
    to_address: str,
    amount: str,
    asset_code: str = "XLM",
    memo: str | None = None,
    idempotency_key: str | None = None,
) -> str:
    """Create a payment request. May return pending_approval when policy requires a human."""
    with _client() as client:
        try:
            return _dump(
                client.payments.create(
                    from_wallet_id=from_wallet_id,
                    to_address=to_address,
                    amount=amount,
                    asset_code=asset_code,
                    memo=memo,
                    idempotency_key=idempotency_key,
                )
            )
        except AgentOSError as exc:
            return _dump({"error": exc.detail, "status_code": exc.status_code})


@mcp.tool()
def get_payment_request(payment_request_id: str) -> str:
    """Get payment request status."""
    with _client() as client:
        return _dump(client.payments.get(payment_request_id))


@mcp.tool()
def execute_transfer(payment_request_id: str, idempotency_key: str | None = None) -> str:
    """Execute a transfer for an approved payment request. Fails if policy/approval blocks it."""
    with _client() as client:
        try:
            return _dump(
                client.transfers.execute(
                    payment_request_id=payment_request_id,
                    idempotency_key=idempotency_key,
                )
            )
        except AgentOSError as exc:
            return _dump({"error": exc.detail, "status_code": exc.status_code})


@mcp.tool()
def get_transfer(transfer_id: str) -> str:
    """Get transfer intent status and network_tx_id."""
    with _client() as client:
        return _dump(client.transfers.get(transfer_id))


@mcp.tool()
def list_ledger_entries() -> str:
    """List audit ledger entries for the organization."""
    with _client() as client:
        return _dump(client.ledger.list())


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
