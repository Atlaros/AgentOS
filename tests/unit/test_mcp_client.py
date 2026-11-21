import socket
import sys
import threading
import time
from pathlib import Path

import pytest
from agentos_mcp.client import McpToolError, connect_mcp
from mcp.client.stdio import StdioServerParameters
from mcp.server.mcpserver import MCPServer

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "echo_mcp_server.py"


def _echo_server() -> MCPServer:
    server = MCPServer(name="echo", version="0.1.0")

    @server.tool()
    def echo(text: str) -> str:
        """Return the text unchanged."""
        return text

    return server


@pytest.mark.asyncio
async def test_inprocess_client_lists_and_calls_tool() -> None:
    async with connect_mcp(_echo_server()) as session:
        assert "echo" in await session.list_tool_names()
        assert await session.call_tool("echo", {"text": "hola"}) == "hola"


@pytest.mark.asyncio
async def test_stdio_client_calls_external_server() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(FIXTURE)])
    async with connect_mcp(params) as session:
        assert await session.call_tool("echo", {"text": "ping"}) == "ping"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_open(port: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("streamable http server did not listen")


@pytest.mark.asyncio
async def test_streamable_http_client_calls_external_server() -> None:
    port = _free_port()
    thread = threading.Thread(
        target=_echo_server().run,
        kwargs={"transport": "streamable-http", "host": "127.0.0.1", "port": port},
        daemon=True,
    )
    thread.start()
    _wait_until_open(port)
    async with connect_mcp(f"http://127.0.0.1:{port}/mcp") as session:
        assert await session.call_tool("echo", {"text": "http"}) == "http"


@pytest.mark.asyncio
async def test_unknown_tool_raises() -> None:
    async with connect_mcp(_echo_server()) as session:
        with pytest.raises(McpToolError):
            await session.call_tool("missing", {})
