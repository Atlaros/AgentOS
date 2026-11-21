"""Tiny external MCP server used to prove AgentOS can consume stdio servers."""

from mcp.server.mcpserver import MCPServer

mcp = MCPServer(name="echo", version="0.1.0")


@mcp.tool()
def echo(text: str) -> str:
    """Return the text unchanged."""
    return text


if __name__ == "__main__":
    mcp.run(transport="stdio")
