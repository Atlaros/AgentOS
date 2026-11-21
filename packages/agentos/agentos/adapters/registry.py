from __future__ import annotations

from agentos.adapters.fake import FakeNetworkAdapter
from agentos.adapters.stellar import StellarTestnetAdapter
from agentos.domain.ports import NetworkAdapter
from agentos.settings import Settings, get_settings

_fake = FakeNetworkAdapter()


def resolve_adapter(provider: str, network: str, settings: Settings | None = None) -> NetworkAdapter:
    """Resolve network adapter. Mainnet is denied in MVP."""
    cfg = settings or get_settings()
    if network in {"public", "mainnet"}:
        raise ValueError("mainnet_denied")
    if provider == "fake" and network == "fake":
        return _fake
    if provider == "stellar" and network == "testnet":
        return StellarTestnetAdapter.from_settings(cfg)
    raise ValueError(f"unsupported_network:{provider}/{network}")


def fake_adapter() -> FakeNetworkAdapter:
    return _fake
