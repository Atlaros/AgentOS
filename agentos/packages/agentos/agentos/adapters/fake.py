from __future__ import annotations

import hashlib
from decimal import Decimal

from agentos.domain.ports import Balance, SubmitResult


class FakeNetworkAdapter:
    """Deterministic lab adapter. No network I/O. No secrets."""

    provider = "fake"
    network = "fake"

    def __init__(self, default_balance: Decimal = Decimal(1000)) -> None:
        self._default_balance = default_balance
        self._submitted: dict[str, SubmitResult] = {}
        self._balances: dict[str, Decimal] = {}

    async def get_balances(self, public_address: str) -> list[Balance]:
        amount = self._balances.get(public_address, self._default_balance)
        return [Balance(asset_code="XLM", amount=amount, issuer=None)]

    async def submit_payment(
        self,
        *,
        from_address: str,
        to_address: str,
        asset_code: str,
        amount: Decimal,
        memo: str | None,
        idempotency_key: str,
    ) -> SubmitResult:
        if idempotency_key in self._submitted:
            return self._submitted[idempotency_key]

        if asset_code != "XLM":
            result = SubmitResult(network_tx_id="", status="failed")
            self._submitted[idempotency_key] = result
            return result

        current = self._balances.get(from_address, self._default_balance)
        if amount > current:
            result = SubmitResult(network_tx_id="", status="failed")
            self._submitted[idempotency_key] = result
            return result

        self._balances[from_address] = current - amount
        self._balances[to_address] = self._balances.get(to_address, Decimal(0)) + amount
        tx_id = "fake_" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]
        result = SubmitResult(network_tx_id=tx_id, status="confirmed")
        self._submitted[idempotency_key] = result
        return result
