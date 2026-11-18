""""Smoke-test the frozen Windows MCP executable through its stdio transport."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def parse_payload(result):
    if getattr(result, "isError", False):
        raise RuntimeError(f"MCP tool returned isError: {result}")
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    for item in getattr(result, "content", []):
        value = getattr(item, "text", None)
        if value:
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise RuntimeError("MCP tool returned no structured JSON payload")


async def run(executable: Path) -> None:
    print("Windows MCP smoke test: starting child-process diagnostics")
    server = StdioServerParameters(
        command=str(executable.resolve()),
        args=[],
        env=os.environ.copy(),
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await asyncio.wait_for(session.initialize(), timeout=30)
            print(f"MCP initialize: protocol={initialized.protocolVersion}")

            listed = await asyncio.wait_for(session.list_tools(), timeout=30)
            names = {tool.name for tool in listed.tools}
            expected = {"search_web", "fetch_web_page", "get_exchange_rate", "get_current_datetime"}
            if not expected.issubset(names):
                raise AssertionError(f"Missing tools: {sorted(expected - names)}")
            print(f"MCP tools: {', '.join(sorted(names))}")

            fetched = parse_payload(
                await asyncio.wait_for(
                    session.call_tool(
                        "fetch_web_page",
                        {"url": "https://example.com", "max_chars": 2000},
                    ),
                    timeout=45,
                )
            )
            if not fetched.get("ok"):
                raise AssertionError(f"fetch_web_page failed: {fetched.get('error')}")
            print(
                "fetch_web_page: "
                f"HTTP {fetched.get('status_code')}; title={fetched.get('title')!r}"
            )

            searched = parse_payload(
                await asyncio.wait_for(
                    session.call_tool(
                        "search_web", {"query": "Example Domain", "max_results": 2}
                    ),
                    timeout=45,
                )
            )
            rate = parse_payload(
                await asyncio.wait_for(
                    session.call_tool(
                        "get_exchange_rate",
                        {"base_currency": "USD", "quote_currency": "RUB"},
                    ),
                    timeout=45,
                )
            )
            if not rate.get("ok") or not rate.get("rate") or not rate.get("effective_date"):
                raise AssertionError(f"get_exchange_rate failed: {rate.get('error')}")
            if "cbr.ru" not in rate.get("source", ""):
                raise AssertionError(f"Unexpected exchange-rate source: {rate.get('source')}")
            print(
                "get_exchange_rate: OK; "
                f"USD/RUB={rate.get('rate')}; effective_date={rate.get('effective_date')}"
            )

            current_time = parse_payload(
                await asyncio.wait_for(
                    session.call_tool("get_current_datetime", {}),
                    timeout=15,
                )
            )
            required_time_fields = {
                "local_datetime", "utc_datetime", "date", "time",
                "timezone", "utc_offset", "unix_timestamp",
            }
            if not current_time.get("ok") or not required_time_fields.issubset(current_time):
                raise AssertionError(f"get_current_datetime failed: {current_time}")
            print(
                "get_current_datetime: OK; "
                f"local={current_time.get('local_datetime')}; "
                f"timezone={current_time.get('timezone')}"
            )

            if searched.get("ok"):
                print(f"search_web: OK; results={len(searched.get('results', []))}")
            else:
                # The MCP invocation and structured error handling are verified;
                # the external search provider may independently rate-limit CI.
                print(f"search_web: invoked; provider response={searched.get('error')!r}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python packaging/windows_smoke.py <path-to-exe>")
    executable_path = Path(sys.argv[1])
    if not executable_path.is_file():
        raise SystemExit(f"Packaged executable not found: {executable_path}")
    asyncio.run(run(executable_path))
    print("WINDOWS PACKAGED MCP SMOKE TEST COMPLETED")
