"""Учебный пример поиска повторяющихся запросов из Урока 16."""


def find_repeated_queries(queries: list[str]) -> list[str]:
    """Возвращает нормализованные запросы, встретившиеся более одного раза."""
    seen: set[str] = set()
    repeated: set[str] = set()

    for query in queries:
        normalized = query.strip().casefold()
        if not normalized:
            continue

        if normalized in seen:
            repeated.add(normalized)
        else:
            seen.add(normalized)

    return sorted(repeated)


if __name__ == "__main__":
    history = [
        "latest Python MCP SDK",
        "  LATEST PYTHON MCP SDK ",
        "official Python MCP documentation",
        "latest Python MCP SDK",
        "   ",
    ]
    print(find_repeated_queries(history))
