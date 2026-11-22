from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class Balance:
    asset_code: str
    amount: Decimal
    issuer: str | None = None


@dataclass(frozen=True)
class SubmitResult:
    network_tx_id: str
    status: str  # submitted | confirmed | failed


class NetworkAdapter(Protocol):
    provider: str
    network: str

    async def get_balances(self, public_address: str) -> list[Balance]:
        ...

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
        ...
