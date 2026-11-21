"""Read-only EVM adapter. It does not sign and it does not submit."""

from __future__ import annotations

from decimal import Decimal

import httpx

from agentos.domain.ports import Balance
from agentos.readiness import CustodyRefused

__all__ = ["CustodyRefused", "EvmNotConnected", "EvmRpcAdapter"]

_WEI = Decimal(10) ** 18


class EvmNotConnected(Exception):
    """No RPC URL was configured for this adapter."""


class EvmRpcAdapter:
    provider = "evm"
    network = "sepolia"

    def __init__(self, *, rpc_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._rpc_url = rpc_url.strip()
        self._client = client

    async def get_balances(self, public_address: str) -> list[Balance]:
        if not self._rpc_url:
            raise EvmNotConnected("evm_not_connected")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getBalance",
            "params": [public_address, "latest"],
        }
        if self._client is None:
            async with httpx.AsyncClient() as client:
                raw = await _post_balance(client, self._rpc_url, payload)
        else:
            raw = await _post_balance(self._client, self._rpc_url, payload)
        wei = Decimal(int(raw, 16))
        return [Balance(asset_code="ETH", amount=wei / _WEI, issuer=None)]

    async def submit_payment(
        self,
        *,
        from_address: str,
        to_address: str,
        asset_code: str,
        amount: Decimal,
        memo: str | None,
        idempotency_key: str,
    ) -> None:
        del from_address, to_address, asset_code, amount, memo, idempotency_key
        raise CustodyRefused("custody_refused")


async def _post_balance(client: httpx.AsyncClient, url: str, payload: dict[str, object]) -> str:
    response = await client.post(url, json=payload)
    response.raise_for_status()
    body = response.json()
    result = body.get("result")
    if not isinstance(result, str) or not result.startswith("0x"):
        raise EvmNotConnected("evm_not_connected")
    return result
