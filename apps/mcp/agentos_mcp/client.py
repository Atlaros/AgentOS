"""MCP client: AgentOS as a consumer of external MCP servers.

This session lists and calls tools on another server. It does not authenticate
to AgentOS and it does not submit payments, transfers, or ledger entries.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, Implementation

ServerTarget = MCPServer | StdioServerParameters | str


class McpToolError(Exception):
    """The external server rejected the tool call."""


class McpSession:
    """Open session against one external MCP server."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def list_tool_names(self) -> list[str]:
        listed = await self._client.list_tools()
        return [tool.name for tool in listed.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        try:
            result = await self._client.call_tool(name, arguments or {})
        except MCPError as exc:
            raise McpToolError(str(exc)) from exc
        text = _result_text(result)
        if result.is_error:
            raise McpToolError(text or name)
        return text


def _result_text(result: CallToolResult) -> str:
    parts: list[str] = []
    for block in result.content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


@asynccontextmanager
async def connect_mcp(server: ServerTarget) -> AsyncIterator[McpSession]:
    """Connect to an in-process server, a stdio command, or a Streamable HTTP URL."""
    async with Client(
        server,
        client_info=Implementation(name="agentos", version="0.1.0"),
    ) as client:
        yield McpSession(client)
