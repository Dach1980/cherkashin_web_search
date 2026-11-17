"""Live HTTPS and MCP stdio smoke test; intended for an isolated CI runner."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from web_search_mcp.web_fetch import web_fetch


def parse_tool_payload(result):
    if getattr(result, "isError", False):
        raise RuntimeError(f"MCP tool returned isError: {result}")
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    for item in getattr(result, "content", []):
        text = getattr(item, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                continue
    raise RuntimeError("MCP tool returned no parseable structured payload.")


async def run_mcp_smoke():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "web_search_mcp.server"],
        env=env,
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            print(f"MCP initialize: protocol={initialized.protocolVersion}")
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            expected = {"search_web", "fetch_web_page"}
            if not expected.issubset(names):
                raise AssertionError(f"Missing MCP tools: {expected - names}")
            print(f"MCP tools discovered: {', '.join(sorted(names))}")

            fetched = parse_tool_payload(
                await session.call_tool(
                    "fetch_web_page",
                    {"url": "https://example.com", "max_chars": 2000},
                )
            )
            if not fetched.get("ok"):
                raise AssertionError(f"MCP fetch_web_page failed: {fetched.get('error')}")
            print(
                "MCP fetch_web_page: "
                f"HTTP {fetched.get('status_code')}; title={fetched.get('title')!r}"
            )

            searched = parse_tool_payload(
                await session.call_tool(
                    "search_web",
                    {"query": "Example Domain", "max_results": 2},
                )
            )
            if searched.get("ok"):
                print(f"MCP search_web: OK; results={len(searched.get('results', []))}")
            else:
                # Tool discovery and invocation are verified, but upstream provider
                # availability is reported separately rather than hiding it.
                print(f"MCP search_web: invoked; provider error={searched.get('error')!r}")


def main():
    print("1. Direct live HTTPS smoke test")
    result = web_fetch("https://example.com", max_chars=2000, timeout=20)
    if not result.get("ok"):
        raise SystemExit(f"Live HTTPS/DNS-pinned fetch failed: {result.get('error')}")
    print(
        "HTTPS fetch: "
        f"HTTP {result.get('status_code')}; title={result.get('title')!r}; "
        f"text_chars={len(result.get('text', ''))}"
    )

    print("2. MCP stdio handshake and tool calls")
    asyncio.run(run_mcp_smoke())
    print("SMOKE TEST COMPLETED")


if __name__ == "__main__":
    main()
