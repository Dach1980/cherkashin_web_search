"""Учебный пример проверки пригодности результата web fetch.

Файл не делает сетевых запросов: он классифицирует подготовленные
результаты, чтобы логику можно было проверять воспроизводимо.
"""

from dataclasses import dataclass


@dataclass
class FetchResult:
    status_code: int
    content_type: str
    text: str


def classify_fetch_result(result: FetchResult) -> str:
    """Вернуть категорию результата загрузки страницы."""
    if result.status_code == 403:
        return "access_forbidden"
    if result.status_code == 404:
        return "page_not_found"
    if result.status_code == 429:
        return "rate_limited"
    if result.status_code >= 500:
        return "server_error"
    if not 200 <= result.status_code < 300:
        return "http_error"

    normalized_type = result.content_type.casefold()
    if "text/html" not in normalized_type and "text/plain" not in normalized_type:
        return "unsupported_content_type"
    if not result.text.strip():
        return "empty_content"

    lowered_text = result.text.casefold()
    block_markers = (
        "captcha",
        "verify you are human",
        "access denied",
        "checking your browser",
    )
    if any(marker in lowered_text for marker in block_markers):
        return "possible_block_page"
    return "ok"


def main() -> None:
    samples = [
        FetchResult(200, "text/html; charset=utf-8", "<h1>Документация</h1>"),
        FetchResult(403, "text/html", "Access denied"),
        FetchResult(200, "application/pdf", ""),
        FetchResult(200, "text/html", "   \n  "),
        FetchResult(429, "text/html", "Too many requests"),
        FetchResult(200, "text/html", "Please verify you are human"),
    ]
    for sample in samples:
        print(sample.status_code, classify_fetch_result(sample))


if __name__ == "__main__":
    main()
