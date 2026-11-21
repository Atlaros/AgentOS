from __future__ import annotations

from typing import Any, Self
from uuid import uuid4

import httpx


class AgentOSError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{status_code}: {detail}")


class AgentOS:
    """Thin REST client. No domain logic — AgentOS API enforces policy."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        organization_id: str,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._organization_id = organization_id
        self._client = httpx.Client(base_url=self._base_url, timeout=timeout)
        self.wallets = _Wallets(self)
        self.payments = _Payments(self)
        self.transfers = _Transfers(self)
        self.ledger = _Ledger(self)
        self.orgs = _Orgs(self)
        self.applications = _Applications(self)
        self.agents = _Agents(self)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-Organization-Id": self._organization_id,
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        response = self._client.request(
            method,
            path,
            json=json,
            headers=self._headers(idempotency_key),
        )
        if response.status_code >= 400:
            detail = response.text
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict) and "detail" in payload:
                detail = str(payload["detail"])
            raise AgentOSError(response.status_code, detail)
        if response.status_code == 204:
            return None
        return response.json()


class _Orgs:
    def __init__(self, root: AgentOS) -> None:
        self._root = root

    def me(self) -> dict[str, Any]:
        return self._root.request("GET", "/v1/organizations/me")


class _Wallets:
    def __init__(self, root: AgentOS) -> None:
        self._root = root

    def list(self) -> list[dict[str, Any]]:
        return self._root.request("GET", "/v1/wallets")

    def link(
        self,
        *,
        public_address: str,
        provider: str = "fake",
        network: str = "fake",
        label: str = "",
    ) -> dict[str, Any]:
        return self._root.request(
            "POST",
            "/v1/wallets/link",
            json={
                "provider": provider,
                "network": network,
                "public_address": public_address,
                "label": label,
            },
        )

    def balances(self, wallet_id: str) -> list[dict[str, Any]]:
        return self._root.request("GET", f"/v1/wallets/{wallet_id}/balances")


class _Payments:
    def __init__(self, root: AgentOS) -> None:
        self._root = root

    def create(
        self,
        *,
        from_wallet_id: str,
        to_address: str,
        amount: str,
        asset_code: str = "XLM",
        memo: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self._root.request(
            "POST",
            "/v1/payment-requests",
            json={
                "from_wallet_id": from_wallet_id,
                "to_address": to_address,
                "amount": amount,
                "asset_code": asset_code,
                "memo": memo,
            },
            idempotency_key=idempotency_key or str(uuid4()),
        )

    def get(self, payment_request_id: str) -> dict[str, Any]:
        return self._root.request("GET", f"/v1/payment-requests/{payment_request_id}")

    def approve(self, payment_request_id: str, *, reason: str | None = None) -> dict[str, Any]:
        return self._root.request(
            "POST",
            f"/v1/payment-requests/{payment_request_id}/approve",
            json={"reason": reason},
        )

    def reject(self, payment_request_id: str, *, reason: str | None = None) -> dict[str, Any]:
        return self._root.request(
            "POST",
            f"/v1/payment-requests/{payment_request_id}/reject",
            json={"reason": reason},
        )


class _Applications:
    def __init__(self, root: AgentOS) -> None:
        self._root = root

    def create(self, *, name: str, scopes: list[str] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name}
        if scopes is not None:
            payload["scopes"] = scopes
        return self._root.request("POST", "/v1/applications", json=payload)


class _Agents:
    def __init__(self, root: AgentOS) -> None:
        self._root = root

    def create(
        self,
        *,
        name: str,
        application_id: str,
        scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name, "application_id": application_id}
        if scopes is not None:
            payload["scopes"] = scopes
        return self._root.request("POST", "/v1/agents", json=payload)

    def list(self) -> list[dict[str, Any]]:
        return self._root.request("GET", "/v1/agents")

    def get(self, agent_id: str) -> dict[str, Any]:
        return self._root.request("GET", f"/v1/agents/{agent_id}")


class _Transfers:
    def __init__(self, root: AgentOS) -> None:
        self._root = root

    def execute(
        self,
        *,
        payment_request_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self._root.request(
            "POST",
            "/v1/transfers",
            json={"payment_request_id": payment_request_id},
            idempotency_key=idempotency_key or str(uuid4()),
        )

    def get(self, transfer_id: str) -> dict[str, Any]:
        return self._root.request("GET", f"/v1/transfers/{transfer_id}")


class _Ledger:
    def __init__(self, root: AgentOS) -> None:
        self._root = root

    def list(self) -> list[dict[str, Any]]:
        return self._root.request("GET", "/v1/ledger")
