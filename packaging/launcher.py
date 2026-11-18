"""Точка входа для упаковки MCP-сервера через PyInstaller.

Сервер и его инструменты остаются в пакете web_search_mcp.
Этот файл только подготавливает frozen runtime и вызывает main().
"""

import multiprocessing

# Must run before importing application dependencies: PyInstaller replaces this
# function with a handler for frozen multiprocessing worker invocations.
multiprocessing.freeze_support()

from web_search_mcp.server import main


if __name__ == "__main__":
    main()
