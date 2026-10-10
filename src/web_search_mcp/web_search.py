from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .config import DEFAULT_MAX_SEARCH_RESULTS, DEFAULT_TIMEOUT_SECONDS

SEARCH_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = "Mozilla/5.0 (compatible; LocalWebSearch/1.0)"


def web_search(query: str, max_results: int = DEFAULT_MAX_SEARCH_RESULTS) -> dict:
    """Find pages and return title, URL, and snippet fields."""
    if not isinstance(query, str) or not query.strip():
        return {"ok": False, "query": str(query), "results": [], "error": "Query must be a non-empty string."}
    if not isinstance(max_results, int) or isinstance(max_results, bool):
        return {"ok": False, "query": query, "results": [], "error": "max_results must be an integer."}
    if not 1 <= max_results <= 10:
        return {"ok": False, "query": query, "results": [], "error": "max_results must be between 1 and 10."}
    try:
        response = httpx.get(
            SEARCH_URL, params={"q": query.strip()},
            headers={"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        return {"ok": False, "query": query, "results": [], "error": f"Search request failed: {error}"}

    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    for item in soup.select(".result"):
        link = item.select_one(".result__title a")
        snippet = item.select_one(".result__snippet")
        if link is None:
            continue
        title = link.get_text(" ", strip=True)
        href = link.get("href", "").strip()
        description = snippet.get_text(" ", strip=True) if snippet else ""
        if not title or not href:
            continue
        results.append({"title": title, "url": urljoin(SEARCH_URL, href), "snippet": description})
        if len(results) >= max_results:
            break
    return {"ok": True, "query": query.strip(), "results": results, "error": None}
