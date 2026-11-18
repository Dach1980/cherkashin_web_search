import logging
import sys

from mcp.server.fastmcp import FastMCP

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


def main() -> None:
    """Run the MCP server over standard input and output."""
    configure_logging()
    logging.getLogger(__name__).info("Starting MCP server: %s", SERVER_NAME)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
