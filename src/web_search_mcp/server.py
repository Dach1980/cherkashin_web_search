import io
import logging
import os
import sys

import anyio

from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server

from .contracts import DateTimeResponse, ExchangeRateResponse, FetchResponse, SearchResponse
from .config import (
    DEFAULT_MAX_PAGE_CHARS,
    DEFAULT_MAX_SEARCH_RESULTS,
    LOG_LEVEL,
    SERVER_NAME,
)
from .current_datetime import get_current_datetime as read_current_datetime
from .exchange_rate import get_exchange_rate as fetch_exchange_rate
from .web_fetch import web_fetch
from .web_search import web_search

mcp = FastMCP(SERVER_NAME)


@mcp.tool()
def search_web(query: str, max_results: int = DEFAULT_MAX_SEARCH_RESULTS) -> SearchResponse:
    """Search the web and return page titles, URLs, and snippets."""
    return web_search(query=query, max_results=max_results)


@mcp.tool()
def fetch_web_page(url: str, max_chars: int = DEFAULT_MAX_PAGE_CHARS) -> FetchResponse:
    """Fetch a web page and return its title and readable text."""
    return web_fetch(url=url, max_chars=max_chars)


@mcp.tool()
def get_exchange_rate(
    base_currency: str = "USD",
    quote_currency: str = "RUB",
) -> ExchangeRateResponse:
    """Use for current exchange-rate questions. Returns the official Bank of Russia rate, effective date, and source; defaults to USD/RUB. Do not guess a rate if this tool fails."""
    return fetch_exchange_rate(base_currency=base_currency, quote_currency=quote_currency)


@mcp.tool()
def get_current_datetime() -> DateTimeResponse:
    """Use for questions about the current date, time, or day of the week. Returns the live system clock on the computer running this MCP server, including its local timezone and UTC offset. This is not necessarily the user's physical location timezone."""
    return read_current_datetime()


def configure_logging() -> None:
    """Send diagnostic logs to stderr so stdio remains available to MCP."""
    logging.basicConfig(
        level=LOG_LEVEL,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _duplicate_stdio_streams():
    """Create UTF-8 streams backed by duplicated OS descriptors.

    MCP's stdio transport wraps the supplied streams in TextIOWrapper objects.
    Giving those wrappers duplicated descriptors prevents their finalization
    from closing the process-wide stdin/stdout used by the PyInstaller
    bootloader during interpreter shutdown.
    """
    stdin_fd = os.dup(sys.stdin.fileno())
    stdout_fd = os.dup(sys.stdout.fileno())
    stdin_raw = os.fdopen(stdin_fd, "rb", buffering=0)
    stdout_raw = os.fdopen(stdout_fd, "wb", buffering=0)
    stdin_buffer = io.BufferedReader(stdin_raw)
    stdout_buffer = io.BufferedWriter(stdout_raw)
    stdin_text = io.TextIOWrapper(
        stdin_buffer, encoding="utf-8", errors="replace"
    )
    stdout_text = io.TextIOWrapper(stdout_buffer, encoding="utf-8")
    return stdin_text, stdout_text


async def _run_stdio_with_duplicated_descriptors() -> None:
    """Run the normal MCP stdio session without transferring stdio ownership."""
    stdin_text, stdout_text = _duplicate_stdio_streams()
    stdin = anyio.wrap_file(stdin_text)
    stdout = anyio.wrap_file(stdout_text)
    try:
        async with stdio_server(stdin=stdin, stdout=stdout) as (read_stream, write_stream):
            await mcp._mcp_server.run(
                read_stream,
                write_stream,
                mcp._mcp_server.create_initialization_options(),
            )
    finally:
        # Close only our duplicated descriptors; the process standard streams
        # remain open for PyInstaller and CPython finalization.
        stdin_text.close()
        stdout_text.close()


def main() -> None:
    """Run the MCP server over standard input and output."""
    configure_logging()
    logging.getLogger(__name__).info("Starting MCP server: %s", SERVER_NAME)
    anyio.run(_run_stdio_with_duplicated_descriptors)


if __name__ == "__main__":
    main()
