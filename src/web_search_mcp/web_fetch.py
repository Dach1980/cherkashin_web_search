"""Ограниченная загрузка публичных HTML-страниц для учебного MCP-сервера."""

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from .config import DEFAULT_MAX_PAGE_CHARS, DEFAULT_TIMEOUT_SECONDS, MAX_REDIRECTS, MAX_RESPONSE_BYTES
from .contracts import FetchResponse

USER_AGENT = "Mozilla/5.0 (compatible; LocalWebFetch/1.1)"
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def _error_result(url: str, error: str, status_code: int | None = None) -> FetchResponse:
    """Возвращает единый формат ошибки."""
    return {
        "ok": False, "url": url, "status_code": status_code, "title": "",
        "text": "", "truncated": False, "error": error,
    }


def _validate_public_url(url: str) -> str | None:
    """Проверяет схему, учётные данные, имя хоста и полученные DNS IP-адреса."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return "URL contains an invalid host or port."

    if parts.scheme.lower() not in ("http", "https"):
        return "Only http and https URLs are accepted."
    if not parts.hostname:
        return "URL must contain a hostname."
    if parts.username is not None or parts.password is not None:
        return "URLs containing username or password are not accepted."

    hostname = parts.hostname.rstrip(".").lower()
    if not hostname:
        return "URL must contain a hostname."
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        return "Local hostnames are not allowed."

    effective_port = port or (443 if parts.scheme.lower() == "https" else 80)
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if not literal_ip.is_global:
            return "Private, loopback, link-local, and non-global IP addresses are not allowed."
        return None

    try:
        addresses = socket.getaddrinfo(hostname, effective_port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return "Hostname could not be resolved."
    if not addresses:
        return "Hostname did not resolve to any address."

    for address_info in addresses:
        try:
            parsed_address = ipaddress.ip_address(address_info[4][0])
        except ValueError:
            return "DNS returned an invalid IP address."
        if not parsed_address.is_global:
            return "Hostname resolves to a private or non-global IP address."
    return None


def _extract_page(html: str, max_chars: int) -> tuple[str, str, bool]:
    """Извлекает заголовок и читаемый текст, удаляя типичные служебные элементы."""
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


def web_fetch(
    url: str,
    max_chars: int = DEFAULT_MAX_PAGE_CHARS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> FetchResponse:
    """Загружает публичную HTML-страницу с лимитом редиректов и размера ответа."""
    if not isinstance(url, str):
        return _error_result("", "URL must be a string.")
    url = url.strip()
    if not url:
        return _error_result(url, "URL must not be empty.")
    if not isinstance(max_chars, int) or isinstance(max_chars, bool):
        return _error_result(url, "max_chars must be an integer.")
    if not 1 <= max_chars <= DEFAULT_MAX_PAGE_CHARS:
        return _error_result(url, f"max_chars must be between 1 and {DEFAULT_MAX_PAGE_CHARS}.")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        return _error_result(url, "timeout must be numeric.")
    if not 0 < timeout <= 60:
        return _error_result(url, "timeout must be greater than 0 and no more than 60 seconds.")

    current_url = url
    for redirect_number in range(MAX_REDIRECTS + 1):
        validation_error = _validate_public_url(current_url)
        if validation_error:
            return _error_result(current_url, validation_error)
        try:
            with httpx.stream(
                "GET", current_url, timeout=float(timeout), follow_redirects=False,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            ) as response:
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        return _error_result(current_url, "Redirect response did not include a Location header.", response.status_code)
                    if redirect_number >= MAX_REDIRECTS:
                        return _error_result(current_url, "Too many redirects.", response.status_code)
                    next_url = urljoin(current_url, location)
                else:
                    next_url = None
                    if response.status_code >= 400:
                        return _error_result(current_url, f"HTTP error: {response.status_code}", response.status_code)
                    content_type = response.headers.get("content-type", "").lower()
                    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                        return _error_result(current_url, f"Expected HTML, received {content_type or 'unknown content type'}.", response.status_code)
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            if int(content_length) > MAX_RESPONSE_BYTES:
                                return _error_result(current_url, "Response body exceeds the configured byte limit.", response.status_code)
                        except ValueError:
                            pass
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            return _error_result(current_url, "Response body exceeds the configured byte limit.", response.status_code)
                        body.extend(chunk)
                    html = bytes(body).decode(response.encoding or "utf-8", errors="replace")
                    title, text, truncated = _extract_page(html, max_chars)
                    if not text:
                        return _error_result(current_url, "No readable text found in HTML.", response.status_code)
                    return {
                        "ok": True, "url": current_url, "status_code": response.status_code,
                        "title": title, "text": text, "truncated": truncated, "error": None,
                    }
        except httpx.TimeoutException:
            return _error_result(current_url, "Request timed out.")
        except httpx.HTTPError as error:
            return _error_result(current_url, f"Request failed: {type(error).__name__}.")
        current_url = next_url
    return _error_result(current_url, "Too many redirects.")
