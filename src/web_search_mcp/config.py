"""Настройки MCP-сервера, читаемые из переменных окружения."""

import os

SERVER_NAME = "web-search-mcp"


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """Читает целое число из окружения и проверяет допустимый диапазон."""
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default

    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer.") from error

    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")

    return value


DEFAULT_TIMEOUT_SECONDS = _env_int("WEB_TIMEOUT_SECONDS", 15, 1, 60)
DEFAULT_MAX_SEARCH_RESULTS = _env_int("WEB_SEARCH_MAX_RESULTS", 5, 1, 10)
DEFAULT_MAX_PAGE_CHARS = _env_int("WEB_FETCH_MAX_PAGE_CHARS", 12_000, 1, 100_000)
MAX_REDIRECTS = _env_int("WEB_FETCH_MAX_REDIRECTS", 3, 0, 10)
MAX_RESPONSE_BYTES = _env_int("WEB_FETCH_MAX_RESPONSE_BYTES", 1_000_000, 1_024, 5_000_000)

LOG_LEVEL = os.getenv("WEB_SEARCH_LOG_LEVEL", "INFO").strip().upper()
_ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
if LOG_LEVEL not in _ALLOWED_LOG_LEVELS:
    allowed = ", ".join(sorted(_ALLOWED_LOG_LEVELS))
    raise ValueError(f"WEB_SEARCH_LOG_LEVEL must be one of: {allowed}.")
