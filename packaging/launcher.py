"""Точка входа для упаковки MCP-сервера через PyInstaller.

Сервер и его инструменты остаются в пакете web_search_mcp.
Этот файл только вызывает существующую функцию main().
"""

from web_search_mcp.server import main


if __name__ == "__main__":
    main()
