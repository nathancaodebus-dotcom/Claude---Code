"""Minimal MCP server used only by tests/test_mcp_client.py, launched as a
real subprocess over stdio so the MCP integration is exercised against an
actual (if tiny) server rather than a mock of the SDK's internals."""
from mcp.server.mcpserver import MCPServer

server = MCPServer("echo-test-server")


@server.tool()
def echo(text: str) -> str:
    """Echoes back the given text, prefixed."""
    return f"echo: {text}"


@server.tool()
def fail(message: str) -> str:
    """Always raises, to exercise MCP error-result handling."""
    raise ValueError(message)


if __name__ == "__main__":
    server.run(transport="stdio")
