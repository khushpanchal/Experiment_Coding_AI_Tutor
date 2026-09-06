from mcp import ClientSession
from mcp.client.sse import sse_client

MCP_URL = "http://127.0.0.1:8000/sse"

async def list_mcp_tools():
    async with sse_client(url=MCP_URL) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            tools = await session.list_tools()
            return tools

async def call_mcp_tool(tool_name: str, arguments: dict):
    async with sse_client(url=MCP_URL) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return result
