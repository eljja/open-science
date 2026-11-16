"""MCP Python SDK v1(FastMCP) / v2(MCPServer) 호환."""
try:  # v1.x
    from mcp.server.fastmcp import FastMCP as Server, Image  # type: ignore
except Exception:  # v2.x: FastMCP -> MCPServer
    from mcp.server.mcpserver import MCPServer as Server, Image  # type: ignore

__all__ = ["Server", "Image"]
