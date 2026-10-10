"""Дополнительный урок 18: асинхронная загрузка статусов публичных страниц.

Учебный пример. Для реального MCP-инструмента сохраните URL-валидацию,
проверку каждого перенаправления и ограничения размера ответа.
"""

import asyncio

import httpx


MAX_CONCURRENT_REQUESTS = 3
REQUEST_TIMEOUT_SECONDS = 10.0


async def fetch_status(
    client: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, str | int | None]:
    """Получить HTTP-статус или вернуть диагностическую ошибку."""
    async with semaphore:
        try:
            response = await client.get(url)
            return {
                "url": url,
                "status_code": response.status_code,
                "error": None,
            }
        except httpx.TimeoutException:
            return {
                "url": url,
                "status_code": None,
                "error": "timeout",
            }
        except httpx.HTTPError as error:
            return {
                "url": url,
                "status_code": None,
                "error": type(error).__name__,
            }


async def main() -> None:
    urls = [
        "https://example.com/",
        "https://www.python.org/",
        "https://httpbin.org/status/404",
    ]

    limits = httpx.Limits(
        max_connections=MAX_CONCURRENT_REQUESTS,
        max_keepalive_connections=MAX_CONCURRENT_REQUESTS,
    )
    timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        follow_redirects=True,
        headers={"User-Agent": "Lesson18AsyncExample/1.0"},
    ) as client:
        results = await asyncio.gather(
            *(fetch_status(client, url, semaphore) for url in urls)
        )

    for result in results:
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
