"""Direct script launcher for the dataset-scoped measurement MCP server."""

from app.measurement_copilot.mcp_server import mcp


if __name__ == "__main__":
    mcp.run()
