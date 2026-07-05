import os
import sys

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters


def get_mcp_toolset(tool_name: str) -> McpToolset:
    """Helper function to create a Stdio-based McpToolset for the local MCP server.

    Args:
        tool_name: The name of the tool to filter/expose from the server.

    Returns:
        McpToolset configured to launch and connect to the local MCP server.
    """
    # Use sys.executable to run with the current environment's Python
    server_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "mcp_server", "server.py")
    )

    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[server_path],
            )
        ),
        tool_filter=[tool_name],
    )
