import asyncio

from agentos_mcp.server import mcp


def test_mcp_tools_match_contract() -> None:
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        "list_wallets",
        "get_balances",
        "create_payment_request",
        "get_payment_request",
        "execute_transfer",
        "get_transfer",
        "list_ledger_entries",
    }
    assert expected <= names
