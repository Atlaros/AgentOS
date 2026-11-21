from decimal import Decimal

import pytest
from agentos.adapters.registry import resolve_adapter
from agentos.adapters.stellar import StellarTestnetAdapter, is_stellar_address
from agentos.settings import Settings
from stellar_sdk import Keypair


def test_format_amount_trims_db_scale() -> None:
    assert StellarTestnetAdapter._format_amount(Decimal("1.000000000000000000")) == "1"
    assert StellarTestnetAdapter._format_amount(Decimal("1.23456789")) == "1.2345678"


def test_is_stellar_address() -> None:
    kp = Keypair.random()
    assert is_stellar_address(kp.public_key)
    assert not is_stellar_address("GFAKESOURCE0001")
    assert not is_stellar_address("not-an-address")


def test_registry_denies_mainnet() -> None:
    with pytest.raises(ValueError, match="mainnet_denied"):
        resolve_adapter("stellar", "public")


def test_registry_resolves_testnet() -> None:
    adapter = resolve_adapter("stellar", "testnet", Settings())
    assert isinstance(adapter, StellarTestnetAdapter)
    assert adapter.network == "testnet"


@pytest.mark.asyncio
async def test_submit_fails_without_secret() -> None:
    adapter = StellarTestnetAdapter(
        horizon_url="https://horizon-testnet.stellar.org",
        network_passphrase="Test SDF Network ; September 2015",
        secret_key=None,
    )
    kp = Keypair.random()
    dest = Keypair.random()
    result = await adapter.submit_payment(
        from_address=kp.public_key,
        to_address=dest.public_key,
        asset_code="XLM",
        amount=Decimal(1),
        memo=None,
        idempotency_key="no-secret",
    )
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_submit_fails_on_address_mismatch() -> None:
    signer = Keypair.random()
    other = Keypair.random()
    dest = Keypair.random()
    adapter = StellarTestnetAdapter(
        horizon_url="https://horizon-testnet.stellar.org",
        network_passphrase="Test SDF Network ; September 2015",
        secret_key=signer.secret,
    )
    result = await adapter.submit_payment(
        from_address=other.public_key,
        to_address=dest.public_key,
        asset_code="XLM",
        amount=Decimal(1),
        memo=None,
        idempotency_key="mismatch",
    )
    assert result.status == "failed"
    assert adapter.signer_public_key() == signer.public_key
