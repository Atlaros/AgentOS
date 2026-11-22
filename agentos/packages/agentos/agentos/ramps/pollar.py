"""Pollar server-side ramps. The secret key stays in the environment."""

from __future__ import annotations

from typing import Any

import httpx


class PollarNotConfigured(Exception):
    """The server secret is missing or is a publishable browser key."""


class PollarRampError(Exception):
    """Pollar rejected a ramp call. The body is the JSON Pollar returned."""

    def __init__(self, code: str, body: dict[str, Any]) -> None:
        super().__init__(code)
        self.code = code
        self.body = body


class PollarClient:
    def __init__(self, *, api_key: str, base_url: str, http: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._http = http

    async def list_routes(self, *, direction: str, external_user_id: str) -> dict[str, object]:
        self._require_secret()
        if direction not in {"ONRAMP", "OFFRAMP"}:
            raise PollarNotConfigured("pollar_not_configured")
        return await self._request(
            "GET",
            f"/ramps/routes?direction={direction}",
            external_user_id=external_user_id,
        )

    async def quote_ramp(
        self,
        *,
        external_user_id: str,
        direction: str,
        fiat_currency: str,
        fiat_rail: str,
        fiat_country: str,
        asset_code: str,
        asset_identifier: str,
        asset_chain: str,
        amount_value: str,
        amount_denomination: str,
    ) -> dict[str, object]:
        self._require_secret()
        if direction not in {"ONRAMP", "OFFRAMP"}:
            raise PollarNotConfigured("pollar_not_configured")
        if asset_chain not in {"STELLAR", "POLYGON", "SOLANA"}:
            raise PollarNotConfigured("pollar_not_configured")
        if amount_denomination not in {"in", "out"}:
            raise PollarNotConfigured("pollar_not_configured")
        payload = {
            "direction": direction,
            "fiat": {
                "currency": fiat_currency,
                "rail": fiat_rail,
                "country": fiat_country,
            },
            "asset": {
                "code": asset_code,
                "identifier": asset_identifier,
                "chain": asset_chain,
            },
            "amount": {
                "value": amount_value,
                "denomination": amount_denomination,
            },
        }
        return await self._request(
            "POST",
            "/ramps/quotes",
            external_user_id=external_user_id,
            json_body=payload,
        )

    async def link_external_wallet(
        self,
        *,
        external_user_id: str,
        chain: str,
        address: str,
    ) -> dict[str, object]:
        self._require_secret()
        if chain not in {"STELLAR", "POLYGON", "SOLANA"}:
            raise PollarNotConfigured("pollar_not_configured")
        return await self._request(
            "PUT",
            f"/ramps/customers/wallets/{chain}",
            external_user_id=external_user_id,
            json_body={"address": address},
        )

    def _require_secret(self) -> None:
        if not self._api_key:
            raise PollarNotConfigured("pollar_not_configured")
        if not self._api_key.startswith("sec_"):
            raise PollarNotConfigured("pollar_secret_key_required")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        external_user_id: str,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        headers = {
            "x-pollar-api-key": self._api_key,
            "x-pollar-external-user-id": external_user_id,
        }
        url = self._base_url + path
        if self._http is None:
            async with httpx.AsyncClient() as http:
                response = await http.request(method, url, headers=headers, json=json_body)
        else:
            response = await self._http.request(method, url, headers=headers, json=json_body)
        body = response.json() if response.content else {}
        if not isinstance(body, dict):
            raise PollarNotConfigured("pollar_not_configured")
        if response.status_code >= 400:
            code = body.get("code")
            raise PollarRampError(str(code or "pollar_error"), body)
        return body
