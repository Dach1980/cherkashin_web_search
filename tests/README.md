# Автоматические тесты

Тесты проекта написаны для pytest. Они подменяют сетевые ответы там, где это возможно, чтобы обычный запуск тестов не зависел от реального поисковика или доступности конкретных сайтов.

Из корня проекта в PowerShell:

~~~powershell
$env:PYTHONPATH = "src"
python -m pytest -q
~~~

Только загрузчик страниц:

~~~powershell
python -m pytest tests/test_web_fetch.py -q
~~~

Только поисковая функция:

~~~powershell
python -m pytest tests/test_web_search.py -q
~~~

Успешный unit-тест не заменяет проверку интеграции MCP с LM Studio. Тесты не подтверждают полный MCP-handshake и не гарантируют защиту от DNS rebinding.
