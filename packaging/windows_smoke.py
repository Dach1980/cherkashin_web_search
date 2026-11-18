"""Smoke-test the frozen Windows MCP executable and capture its process output."""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import mcp.client.stdio as mcp_stdio
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


def process_return_code(process):
    """Read the exit code from either AnyIO's Process or MCP's Windows fallback."""
    popen = getattr(process, "popen", None)
    returncode = getattr(popen, "returncode", None) if popen is not None else None
    if returncode is None:
        returncode = getattr(process, "returncode", None)
    return returncode


async def run(executable: Path) -> None:
    executable = executable.resolve()
    stderr_path = Path("windows-smoke-server.stderr.log").resolve()
    captured_processes = []

    # Capture the exact process object created by MCP's Windows stdio transport.
    # This lets the smoke test assert its exit code after stdio_client shuts it down.
    original_create_windows_process = mcp_stdio.create_windows_process

    async def capture_windows_process(*args, **kwargs):
        process = await original_create_windows_process(*args, **kwargs)
        captured_processes.append(process)
        return process

    mcp_stdio.create_windows_process = capture_windows_process
    failure = None

    server = StdioServerParameters(
        command=str(executable),
        args=[],
        env=os.environ.copy(),
    )

    try:
        # A real file handle is used because Windows CreateProcess stderr redirection
        # requires an OS file descriptor; StringIO cannot be used here.
        with stderr_path.open("wb") as server_stderr:
            async with stdio_client(server, errlog=server_stderr) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    initialized = await asyncio.wait_for(session.initialize(), timeout=30)
                    print(f"MCP initialize: protocol={initialized.protocolVersion}")

                    listed = await asyncio.wait_for(session.list_tools(), timeout=30)
                    names = {tool.name for tool in listed.tools}
                    expected = {
                        "search_web",
                        "fetch_web_page",
                        "get_exchange_rate",
                        "get_current_datetime",
                    }
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
                        raise AssertionError(
                            f"fetch_web_page failed: {fetched.get('error')}"
                        )
                    print(
                        "fetch_web_page: "
                        f"HTTP {fetched.get('status_code')}; title={fetched.get('title')!r}"
                    )

                    searched = parse_payload(
                        await asyncio.wait_for(
                            session.call_tool(
                                "search_web",
                                {"query": "Example Domain", "max_results": 2},
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
                    if (
                        not rate.get("ok")
                        or not rate.get("rate")
                        or not rate.get("effective_date")
                    ):
                        raise AssertionError(
                            f"get_exchange_rate failed: {rate.get('error')}"
                        )
                    if "cbr.ru" not in rate.get("source", ""):
                        raise AssertionError(
                            f"Unexpected exchange-rate source: {rate.get('source')}"
                        )
                    print(
                        "get_exchange_rate: OK; "
                        f"USD/RUB={rate.get('rate')}; "
                        f"effective_date={rate.get('effective_date')}"
                    )

                    current_time = parse_payload(
                        await asyncio.wait_for(
                            session.call_tool("get_current_datetime", {}),
                            timeout=15,
                        )
                    )
                    required_time_fields = {
                        "local_datetime",
                        "utc_datetime",
                        "date",
                        "time",
                        "timezone",
                        "utc_offset",
                        "unix_timestamp",
                    }
                    if (
                        not current_time.get("ok")
                        or not required_time_fields.issubset(current_time)
                    ):
                        raise AssertionError(
                            f"get_current_datetime failed: {current_time}"
                        )
                    print(
                        "get_current_datetime: OK; "
                        f"local={current_time.get('local_datetime')}; "
                        f"timezone={current_time.get('timezone')}"
                    )

                    if searched.get("ok"):
                        print(
                            "search_web: OK; "
                            f"results={len(searched.get('results', []))}"
                        )
                    else:
                        # Provider rate limits are external to the MCP transport.
                        print(
                            "search_web: invoked; "
                            f"provider response={searched.get('error')!r}"
                        )
    except BaseException as exc:
        failure = exc
    finally:
        mcp_stdio.create_windows_process = original_create_windows_process

    # stdio_client has now closed/waited for the child. Read the child's stderr
    # independently of this Python smoke-test process's own stdout/stderr.
    child_stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    print(f"SERVER STDERR LOG: {stderr_path}")
    if child_stderr:
        print("----- BEGIN PACKAGED SERVER STDERR -----")
        print(child_stderr, end="" if child_stderr.endswith("\n") else "\n")
        print("----- END PACKAGED SERVER STDERR -----")
    else:
        print("PACKAGED SERVER STDERR: <empty>")

    if len(captured_processes) != 1:
        raise RuntimeError(
            "Expected exactly one packaged MCP child process; "
            f"captured {len(captured_processes)}"
        )

    child_process = captured_processes[0]
    returncode = process_return_code(child_process)
    if returncode is None:
        returncode = await child_process.wait()
    print(f"PACKAGED SERVER EXIT CODE: {returncode}")

    diagnostics = []
    if failure is not None:
        diagnostics.append(f"MCP session failed: {failure!r}")
    if returncode != 0:
        diagnostics.append(f"Packaged server exited with code {returncode}")
    if re.search(
        r"Traceback \(most recent call last\):|"
        r"ValueError:\\s*I/O operation on closed file|"
        r"I/O operation on closed file",
        child_stderr,
        flags=re.IGNORECASE,
    ):
        diagnostics.append("Packaged server stderr contains a traceback/closed-I/O error")

    if diagnostics:
        raise RuntimeError("; ".join(diagnostics))

    print("PACKAGED SERVER STDERR CHECK: clean for targeted errors")
    print("WINDOWS PACKAGED MCP SMOKE TEST COMPLETED")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python packaging/windows_smoke.py <path-to-exe>")
    executable_path = Path(sys.argv[1])
    if not executable_path.is_file():
        raise SystemExit(f"Packaged executable not found: {executable_path}")
    asyncio.run(run(executable_path))
