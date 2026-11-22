from decimal import Decimal

import pytest
from agentos.adapters.fake import FakeNetworkAdapter


@pytest.mark.asyncio
async def test_fake_balances_and_transfer() -> None:
    adapter = FakeNetworkAdapter(default_balance=Decimal(100))
    balances = await adapter.get_balances("GSOURCE")
    assert balances[0].amount == Decimal(100)

    result = await adapter.submit_payment(
        from_address="GSOURCE",
        to_address="GDEST",
        asset_code="XLM",
        amount=Decimal(25),
        memo=None,
        idempotency_key="idem-1",
    )
    assert result.status == "confirmed"
    assert result.network_tx_id.startswith("fake_")

    replay = await adapter.submit_payment(
        from_address="GSOURCE",
        to_address="GDEST",
        asset_code="XLM",
        amount=Decimal(25),
        memo=None,
        idempotency_key="idem-1",
    )
    assert replay.network_tx_id == result.network_tx_id

    after = await adapter.get_balances("GSOURCE")
    assert after[0].amount == Decimal(75)
