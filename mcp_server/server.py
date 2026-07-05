import os
import sys

from mcp.server.fastmcp import FastMCP

# Add the project root to path to allow importing local modules if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.tools import find_missing_ingredients, get_nutrition, search_recipe

# Create FastMCP server
mcp = FastMCP("LeftoversGPT-MCP-Server")

# Register the tools with the MCP server
mcp.tool(name="search_recipe")(search_recipe)
mcp.tool(name="get_nutrition")(get_nutrition)
mcp.tool(name="find_missing_ingredients")(find_missing_ingredients)

if __name__ == "__main__":
    # The server runs via standard I/O (stdio) transport by default
    mcp.run()
