"""Структуры данных, возвращаемые инструментами MCP."""

from typing import TypedDict


class SearchResult(TypedDict):
    """Один результат веб-поиска."""

    title: str
    url: str
    snippet: str


class SearchResponse(TypedDict):
    """Единый контракт ответа инструмента поиска."""

    ok: bool
    query: str
    results: list[SearchResult]
    error: str | None


class FetchResponse(TypedDict):
    """Единый контракт ответа инструмента загрузки страницы."""

    ok: bool
    url: str
    status_code: int | None
    title: str
    text: str
    truncated: bool
    error: str | None
