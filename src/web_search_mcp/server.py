from mcp.server.fastmcp import FastMCP

from .config import DEFAULT_MAX_PAGE_CHARS, DEFAULT_MAX_SEARCH_RESULTS, SERVER_NAME
from .web_fetch import web_fetch
from .web_search import web_search

mcp = FastMCP(SERVER_NAME)


@mcp.tool()
def search_web(query: str, max_results: int = DEFAULT_MAX_SEARCH_RESULTS) -> dict:
    """Search the web and return page titles, URLs, and snippets."""
    return web_search(query=query, max_results=max_results)


@mcp.tool()
def fetch_web_page(url: str, max_chars: int = DEFAULT_MAX_PAGE_CHARS) -> dict:
    """Fetch a web page and return its title and readable text."""
    return web_fetch(url=url, max_chars=max_chars)


def main() -> None:
    """Run the MCP server over standard input and output."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
