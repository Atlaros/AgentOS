"""Trustless Work escrow calls. This client never signs the returned XDR."""

from __future__ import annotations

from decimal import Decimal

import httpx


class TrustlessWorkNotConfigured(Exception):
    """No Trustless Work API key is configured."""


class TrustlessWorkClient:
    def __init__(self, *, api_key: str, base_url: str, http: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._http = http

    async def fund_escrow_unsigned(self, *, contract_id: str, signer: str, amount: Decimal) -> str:
        if not self._api_key:
            raise TrustlessWorkNotConfigured("trustless_work_not_connected")
        payload = {
            "contractId": contract_id,
            "signer": signer,
            "amount": format(amount, "f"),
        }
        headers = {"x-api-key": self._api_key}
        url = self._base_url + "/escrow/multi-release/fund-escrow"
        if self._http is None:
            async with httpx.AsyncClient() as http:
                response = await http.post(url, json=payload, headers=headers)
        else:
            response = await self._http.post(url, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
        xdr = body.get("unsignedTransaction") if isinstance(body, dict) else None
        if not isinstance(xdr, str) or not xdr:
            raise TrustlessWorkNotConfigured("trustless_work_not_connected")
        return xdr
