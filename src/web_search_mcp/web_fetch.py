from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from .config import DEFAULT_MAX_PAGE_CHARS, DEFAULT_TIMEOUT_SECONDS

USER_AGENT = "Mozilla/5.0 (compatible; LocalWebFetch/1.0)"


def _error_result(url: str, error: str, status_code: int | None = None) -> dict:
    return {
        "ok": False, "url": url, "status_code": status_code, "title": "",
        "text": "", "truncated": False, "error": error,
    }


def _extract_page(html: str, max_chars: int) -> tuple[str, str, bool]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title is not None else ""
    for element in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        element.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = " ".join(main.get_text(" ", strip=True).split())
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return title, text, truncated


def web_fetch(url: str, max_chars: int = DEFAULT_MAX_PAGE_CHARS, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict:
    if not isinstance(url, str):
        return _error_result("", "URL must be a string.")
    url = url.strip()
    if not url:
        return _error_result(url, "URL must not be empty.")
    if not isinstance(max_chars, int) or isinstance(max_chars, bool):
        return _error_result(url, "max_chars must be an integer.")
    if max_chars < 1:
        return _error_result(url, "max_chars must be greater than zero.")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        return _error_result(url, "timeout must be numeric.")
    if timeout <= 0:
        return _error_result(url, "timeout must be greater than zero.")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return _error_result(url, "Only absolute http/https URLs are accepted.")
    try:
        response = httpx.get(
            url, timeout=float(timeout), follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        return _error_result(url, f"HTTP error: {error.response.status_code}", error.response.status_code)
    except httpx.RequestError as error:
        return _error_result(url, f"Request failed: {error}")
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        return _error_result(url, f"Expected HTML, received {content_type or 'unknown content type'}.", response.status_code)
    title, text, truncated = _extract_page(response.text, max_chars)
    if not text:
        return _error_result(url, "No readable text found in HTML.", response.status_code)
    return {
        "ok": True, "url": str(response.url), "status_code": response.status_code,
        "title": title, "text": text, "truncated": truncated, "error": None,
    }
