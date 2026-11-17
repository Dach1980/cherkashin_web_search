# Автоматические тесты

Тесты проекта написаны для pytest. Сетевые ответы подменяются, поэтому обычный запуск не зависит от доступности реального поисковика или конкретных сайтов.

## Установка зависимостей

Из корня проекта:

~~~powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
~~~

## Запуск полного набора

~~~powershell
$env:PYTHONPATH = "src"
python -m pytest -q
~~~

Только загрузчик страниц:

~~~powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_web_fetch.py -q
~~~

Только поисковая функция:

~~~powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_web_search.py -q
~~~

## Проверки DNS pinning

Тесты загрузчика дополнительно проверяют, что:
- URL сетевого запроса содержит проверенный IP-литерал, а не исходный hostname;
- для HTTPS сохраняются исходные Host и TLS SNI;
- исходное имя разрешается один раз до запроса;
- смешанный публичный/приватный DNS-ответ отклоняется;
- редирект на loopback отклоняется до второго сетевого запроса.

Эти тесты подтверждают построение запроса с закреплённым IP на уровне HTTPX. Они не заменяют сетевой smoke test и проверку TLS/прокси на целевых Windows-системах.

GitHub Actions запускает полный набор тестов при push в `main` и при pull request. Успешный unit-тест не заменяет проверку MCP-handshake и интеграции с LM Studio.
