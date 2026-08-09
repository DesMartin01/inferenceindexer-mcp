"""Integration test: connects to the InferenceIndexer MCP server over stdio
using the official MCP client SDK, lists tools, and calls one tool against
the live API. Simulates what a real agent does.

Run:
  II_SSR_SECRET=... uv run python test_mcp_integration.py
"""

import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    import os

    env = dict(os.environ)
    params = StdioServerParameters(
        command=os.path.join(
            os.path.dirname(__file__), ".venv", "bin", "python"
        ),
        args=["-m", "inferenceindexer_mcp.server"],
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print("server name:", init.serverInfo.name)
            print("server version:", init.serverInfo.version)

            tools = await session.list_tools()
            print("tools found:", len(tools.tools))
            names = sorted(t.name for t in tools.tools)
            print("  " + ", ".join(names))

            # Call one read-only tool against the live API.
            res = await session.call_tool("search_models", {"limit": 1})
            print("search_models result (text):")
            for c in res.content:
                text = getattr(c, "text", None)
                if text:
                    print(" ", str(text)[:300])


if __name__ == "__main__":
    asyncio.run(main())