# Урок № 10. Превращаем Python-функции в MCP-сервер

## 1. Цель урока

В уроке № 8 мы познакомились с поиском веб-страниц, а в уроке № 9 — с загрузкой найденной страницы и извлечением читаемого текста. Пока эти операции являются обычными функциями Python. LM Studio не может вызвать их автоматически только потому, что они существуют в проекте.

Теперь объединим функции в MCP-сервер. Он объявит инструменты, опишет их входные параметры, примет запрос от MCP-клиента, передаст его нужной Python-функции и вернёт результат. Это основной шаг от отдельных учебных функций к приложению, которое можно подключить к LM Studio.

MCP-сервер не является языковой моделью или поисковой системой. Он предоставляет разрешённые операции. Модель решает, когда вызвать инструмент; Python выполняет операцию и возвращает данные.

## 2. Иностранные термины и определения

**MCP (Model Context Protocol — протокол контекста модели)** — протокол взаимодействия приложений с внешними инструментами и источниками данных. В нашем проекте он позволяет LM Studio обнаружить инструменты Python-сервера и запросить их выполнение.

**Протокол (protocol)** — согласованные правила обмена сообщениями: формат запроса, поля данных, формат ответа и обработка ошибок.

**Сервер (server)** — программа, которая предоставляет другим программам функции или данные. Здесь сервер ожидает запросов MCP-клиента.

**Клиент (client)** — программа, которая подключается к серверу и отправляет ему запросы. Клиентом в нашем сценарии выступает часть LM Studio, работающая с MCP.

**Инструмент (tool)** — именованная операция, которую клиент может представить языковой модели для вызова. Наши инструменты будут называться search_web и fetch_web_page.

**SDK (Software Development Kit — комплект средств разработки)** — библиотека и набор средств, упрощающих работу с определённой технологией. MCP SDK для Python берёт на себя детали протокола.

**FastMCP** — высокоуровневый интерфейс MCP SDK для Python. Он позволяет создать сервер и регистрировать инструменты на основе обычных функций.

**Декоратор (decorator)** — конструкция Python, которая применяется к функции или классу и добавляет или изменяет поведение объекта. Запись @mcp.tool() регистрирует следующую функцию как MCP-инструмент.

**Схема (schema)** — формальное описание структуры данных. Схема инструмента сообщает клиенту, какие параметры он принимает и какие у них типы.

**Транспорт (transport)** — способ передачи сообщений между процессами. Для локального MCP-сервера мы используем stdio.

**stdio (standard input/output — стандартный ввод и вывод)** — стандартные потоки ввода и вывода процесса. При использовании stdio протокольные сообщения передаются через эти потоки. Обычные отладочные сообщения в stdout могут сломать обмен.

**JSON-RPC** — формат обмена запросами и ответами для удалённого вызова процедур. В этом уроке не будем собирать JSON-RPC вручную: это делает SDK.

**Аннотация типа (type annotation)** — подсказка о предполагаемом типе параметра или результата функции. MCP SDK использует аннотации для описания входных данных инструмента.

**Docstring** — строка документации внутри функции или модуля, объясняющая его назначение. Описание инструмента важно, чтобы модель правильно поняла, когда его использовать.

## 3. Архитектура проекта

~~~text
LM Studio / MCP-клиент
        |
        | MCP через stdio
        v
MCP-сервер FastMCP
        |
        +---- search_web ----> web_search()
        |
        +---- fetch_web_page -> web_fetch()
~~~

Архитектура состоит из четырёх частей:

1. LM Studio — приложение, в котором работает языковая модель.
2. MCP-клиент — часть приложения, которая подключается к серверу и обнаруживает инструменты.
3. MCP-сервер — программа на Python, которая принимает вызовы и регистрирует доступные инструменты.
4. Прикладные функции — обычные функции поиска и загрузки страниц. Они не должны зависеть от MCP.

Такое разделение уменьшает дублирование. Если мы изменим поискового провайдера, можно менять web_search.py, не переписывая сервер. Если изменится способ регистрации MCP-инструментов, изменения в основном останутся в server.py.

## 4. Проверяем зависимости

В корне проекта есть requirements.txt с зависимостями httpx, beautifulsoup4, mcp и pytest. В активированном виртуальном окружении выполните:

~~~powershell
python -m pip install -r requirements.txt
~~~

Проверьте доступность FastMCP:

~~~powershell
python -c "from mcp.server.fastmcp import FastMCP; print('FastMCP доступен')"
~~~

Ожидаемый вывод:

~~~text
FastMCP доступен
~~~

Если возникает ModuleNotFoundError, возможно, зависимости установлены в другом Python-окружении. Сравните вывод команд python --version и python -m pip --version в том же терминале, где запускаете проект.

## 5. Создаём прикладную функцию web_search

Создайте файл src/web_search_mcp/web_search.py. Это обычная функция Python, которую можно вызывать независимо от MCP:

~~~python
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .config import DEFAULT_MAX_SEARCH_RESULTS, DEFAULT_TIMEOUT_SECONDS

SEARCH_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = "Mozilla/5.0 (compatible; LocalWebSearch/1.0)"


def web_search(query: str, max_results: int = DEFAULT_MAX_SEARCH_RESULTS) -> dict:
    """Find pages and return title, URL, and snippet fields."""
    if not isinstance(query, str) or not query.strip():
        return {"ok": False, "query": str(query), "results": [], "error": "Query must be a non-empty string."}
    if not isinstance(max_results, int) or isinstance(max_results, bool):
        return {"ok": False, "query": query, "results": [], "error": "max_results must be an integer."}
    if not 1 <= max_results <= 10:
        return {"ok": False, "query": query, "results": [], "error": "max_results must be between 1 and 10."}

    try:
        response = httpx.get(
            SEARCH_URL,
            params={"q": query.strip()},
            headers={"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        return {"ok": False, "query": query, "results": [], "error": f"Search request failed: {error}"}

    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    for item in soup.select(".result"):
        link = item.select_one(".result__title a")
        snippet = item.select_one(".result__snippet")
        if link is None:
            continue
        title = link.get_text(" ", strip=True)
        href = link.get("href", "").strip()
        description = snippet.get_text(" ", strip=True) if snippet else ""
        if not title or not href:
            continue
        results.append({"title": title, "url": urljoin(SEARCH_URL, href), "snippet": description})
        if len(results) >= max_results:
            break

    return {"ok": True, "query": query.strip(), "results": results, "error": None}
~~~

Разбор:

- from urllib.parse import urljoin импортирует функцию, которая превращает относительный адрес ссылки в полный URL.
- httpx выполняет HTTP-запрос, а BeautifulSoup разбирает HTML поисковой страницы.
- Относительный импорт from .config означает, что настройки импортируются из другого модуля того же пакета.
- Проверки if отклоняют пустой запрос и некорректный лимит.
- try/except обрабатывает ошибки HTTP-запроса.
- Цикл for перебирает найденные HTML-элементы.
- continue пропускает результат без ссылки.
- append добавляет подготовленный словарь в список.
- break завершает цикл, когда достигнут лимит результатов.
- Функция возвращает словарь с признаком ok, запросом, списком результатов и полем error.

Поиск через HTML-страницу — учебный вариант: разметка и доступность провайдера могут меняться. Не пытайтесь обходить CAPTCHA или ограничения сервиса.

## 6. Создаём прикладную функцию web_fetch

Создайте файл src/web_search_mcp/web_fetch.py:

~~~python
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from .config import DEFAULT_MAX_PAGE_CHARS, DEFAULT_TIMEOUT_SECONDS

USER_AGENT = "Mozilla/5.0 (compatible; LocalWebFetch/1.0)"


def _error_result(url: str, error: str, status_code: int | None = None) -> dict:
    return {
        "ok": False, "url": url, "status_code": status_code, "title": "",
        "text": "", "truncated": False, "error": error,
    }


def _extract_page(html: str, max_chars: int) -> tuple[str, str, bool]:
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


def web_fetch(url: str, max_chars: int = DEFAULT_MAX_PAGE_CHARS, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict:
    if not isinstance(url, str):
        return _error_result("", "URL must be a string.")
    url = url.strip()
    if not url:
        return _error_result(url, "URL must not be empty.")
    if not isinstance(max_chars, int) or isinstance(max_chars, bool):
        return _error_result(url, "max_chars must be an integer.")
    if max_chars < 1:
        return _error_result(url, "max_chars must be greater than zero.")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        return _error_result(url, "timeout must be numeric.")
    if timeout <= 0:
        return _error_result(url, "timeout must be greater than zero.")

    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return _error_result(url, "Only absolute http/https URLs are accepted.")

    try:
        response = httpx.get(
            url, timeout=float(timeout), follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        return _error_result(url, f"HTTP error: {error.response.status_code}", error.response.status_code)
    except httpx.RequestError as error:
        return _error_result(url, f"Request failed: {error}")

    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        return _error_result(url, f"Expected HTML, received {content_type or 'unknown content type'}.", response.status_code)

    title, text, truncated = _extract_page(response.text, max_chars)
    if not text:
        return _error_result(url, "No readable text found in HTML.", response.status_code)

    return {
        "ok": True, "url": str(response.url), "status_code": response.status_code,
        "title": title, "text": text, "truncated": truncated, "error": None,
    }
~~~

Это учебная версия сетевого инструмента. Она проверяет схему URL, но пока не реализует полноценную защиту от SSRF, частных IP-адресов, опасных перенаправлений и DNS rebinding. Не публикуйте её как открытый сетевой сервис. В уроке № 11 отдельно займёмся безопасностью и тестами.

## 7. Создаём MCP-сервер

Создайте файл src/web_search_mcp/server.py:

~~~python
from mcp.server.fastmcp import FastMCP

from .config import DEFAULT_MAX_PAGE_CHARS, DEFAULT_MAX_SEARCH_RESULTS, SERVER_NAME
from .web_fetch import web_fetch
from .web_search import web_search

mcp = FastMCP(SERVER_NAME)


@mcp.tool()
def search_web(query: str, max_results: int = DEFAULT_MAX_SEARCH_RESULTS) -> dict:
    """Search the web and return page titles, URLs, and snippets."""
    return web_search(query=query, max_results=max_results)


@mcp.tool()
def fetch_web_page(url: str, max_chars: int = DEFAULT_MAX_PAGE_CHARS) -> dict:
    """Fetch a web page and return its title and readable text."""
    return web_fetch(url=url, max_chars=max_chars)


def main() -> None:
    """Run the MCP server over standard input and output."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
~~~

### 7.1. Создание сервера

Строка mcp = FastMCP(SERVER_NAME) создаёт объект сервера и передаёт ему имя из config.py. Настройка находится в одном месте, поэтому имя не приходится дублировать в нескольких файлах.

### 7.2. Новый декоратор @mcp.tool()

Декоратор @mcp.tool() — ключевая новая конструкция урока. Он регистрирует следующую функцию как инструмент MCP. SDK использует имя функции, её docstring и аннотации типов, чтобы описать инструмент клиенту.

Регистрация не выполняет поиск немедленно. Она сообщает серверу, что такая операция доступна. Сам поиск начнётся, когда клиент запросит вызов инструмента.

### 7.3. Аннотации типов и параметры

В объявлении функции search_web:

~~~python
def search_web(query: str, max_results: int = DEFAULT_MAX_SEARCH_RESULTS) -> dict:
~~~

- query: str означает, что параметр query ожидается строкой;
- max_results: int — целочисленный параметр;
- знак равенства задаёт значение по умолчанию;
- -> dict обозначает ожидаемый тип возвращаемого результата.

Аннотации помогают SDK сформировать схему, но сами по себе не заменяют валидацию. Поэтому прикладные функции также проверяют входные значения.

### 7.4. Почему сервер вызывает уже существующую функцию?

~~~python
return web_search(query=query, max_results=max_results)
~~~

Серверный слой должен оставаться тонким: принять вызов MCP и передать его прикладной функции. Здесь не нужно дублировать HTTP-запрос и разбор HTML. Это уменьшает повторение кода и облегчает тестирование.

Запись query=query — передача аргумента по имени. Слева указано имя параметра вызываемой функции, справа — значение, полученное серверной функцией. Такая форма явная и удобная для чтения.

### 7.5. Запуск через stdio

~~~python
def main() -> None:
    mcp.run(transport="stdio")
~~~

Метод run запускает сервер. Параметр transport="stdio" выбирает стандартные потоки ввода и вывода для обмена сообщениями MCP.

**Критически важно:** не добавляйте обычные print() для отладки в код, который работает через stdio. Текст в stdout может нарушить поток протокольных сообщений. Для диагностики используйте stderr или правильно настроенный логгер, который пишет в stderr. Не записывайте в логи секреты и чувствительные данные.

## 8. Запуск сервера в PowerShell

В корне проекта активируйте виртуальное окружение и выполните:

~~~powershell
$env:PYTHONPATH = "src"
python -m web_search_mcp.server
~~~

Первая команда добавляет каталог src в путь поиска импортируемых модулей для текущего сеанса PowerShell. Вторая запускает модуль как программу.

Если запуск прошёл успешно, терминал может выглядеть пустым. Это нормально: сервер ждёт сообщения MCP-клиента. Он не обязан печатать приветствие. Остановить процесс во время ручного тестирования можно сочетанием Ctrl+C.

Проверьте импорт функций отдельной командой:

~~~powershell
$env:PYTHONPATH = "src"
python -c "from web_search_mcp.web_search import web_search; from web_search_mcp.web_fetch import web_fetch; print('Обе функции импортированы')"
~~~

Ожидаемый вывод:

~~~text
Обе функции импортированы
~~~

Эта проверка подтверждает импорт модулей, но ещё не доказывает, что MCP-клиент обнаружил инструменты. Для полного протокольного теста клиент должен подключиться, запросить список инструментов и вызвать их. Автоматические тесты добавим в уроке № 11, а подключение к LM Studio подробно выполним в уроке № 12.

## 9. Как инструменты будут работать в LM Studio

После настройки сервера клиент получает список доступных инструментов и их описания. Когда модель решает, что ей нужен интернет, она может вызвать search_web с query и max_results. Получив список результатов, модель выбирает ссылку и вызывает fetch_web_page с url и max_chars.

Типовой сценарий:

1. Пользователь задаёт вопрос.
2. Модель определяет, что ей нужны внешние сведения.
3. Модель вызывает инструмент поиска.
4. Python-сервер возвращает заголовки, URL и описания результатов.
5. Модель выбирает подходящую страницу.
6. Модель вызывает инструмент загрузки.
7. Сервер возвращает заголовок и извлечённый текст.
8. Модель формирует ответ на основе полученного материала.

Наличие инструмента не означает, что модель обязана вызывать его при каждом вопросе. Решение зависит от модели, настроек приложения и контекста запроса. Если модель повторяет один и тот же вызов, причина может быть не только в сервере: нужно проверить результат инструмента, его описание, поддержку tool calling моделью и управление циклом вызовов.

## 10. Частые ошибки

**ModuleNotFoundError: No module named 'mcp'.** MCP SDK не установлен в активном окружении. Выполните python -m pip install -r requirements.txt и проверьте путь к pip.

**ModuleNotFoundError: No module named 'web_search_mcp'.** Для структуры src нужен корректный путь импорта. Из корня проекта задайте $env:PYTHONPATH = "src" или позднее установите проект в режиме разработки после настройки упаковки.

**ImportError для FastMCP.** Проверьте версию пакета mcp и API этой версии. Не смешивайте примеры разных версий SDK. Позже зафиксируем проверенные версии зависимостей.

**Сервер запускается, но ничего не пишет.** Для stdio это нормальное ожидание входящих протокольных сообщений. Пустой терминал сам по себе не подтверждает и не опровергает успешное соединение.

**Клиент не видит инструменты.** Проверьте путь к Python, рабочую директорию, доступность зависимостей и наличие ошибок импорта. Для подтверждения нужен запрос списка инструментов со стороны клиента.

**Поиск возвращает ошибку.** Причиной может быть сеть или изменение HTML поискового провайдера. Посмотрите поле error. Не делайте вывод, что MCP сломан, если сбой произошёл внутри web_search.

**Протокол ломается после добавления print().** Удалите обычный вывод из stdout. В stdio этот поток используется для сообщений протокола; диагностику отправляйте в stderr.

**Модель не вызывает инструменты.** Проверьте настройки клиента, доступность инструментов и поддержку вызовов инструментов используемой моделью. MCP предоставляет механизм, но не гарантирует, что любая модель будет правильно им пользоваться.

## 11. Практические задания

1. Объясните разницу между обычной функцией Python и MCP-инструментом.
2. Найдите создание объекта FastMCP и объясните, зачем он нужен.
3. Измените описание search_web и объясните, почему описание должно быть точным.
4. Измените значение по умолчанию max_results на 3 и проверьте ограничения в прикладной функции.
5. Объясните, почему в server.py нет HTTP-запроса.
6. Найдите оба декоратора @mcp.tool() и назовите регистрируемые инструменты.
7. Уберите PYTHONPATH и попробуйте запустить модуль. Объясните возникшую ошибку.
8. Объясните, почему print() опасен для stdio-сервера.
9. Нарисуйте схему обмена между LM Studio, клиентом, сервером и функциями.
10. Составьте список минимум из пяти проверок перед подключением сервера к LM Studio.

## 12. Контрольные вопросы

1. Что такое MCP?
2. Какую задачу решает MCP SDK?
3. Чем клиент отличается от сервера?
4. Что такое MCP-инструмент?
5. Что такое FastMCP?
6. Что делает декоратор @mcp.tool()?
7. Что такое схема входных данных?
8. Почему аннотации типов полезны при регистрации инструмента?
9. Почему аннотации типов не заменяют проверку данных?
10. Что означает stdio?
11. Почему нельзя писать отладочные сообщения в stdout MCP-сервера?
12. Куда направлять отладочные сообщения?
13. Что такое JSON-RPC?
14. Почему не нужно вручную формировать JSON-RPC, когда этим занимается SDK?
15. Чем прикладная функция отличается от серверной обёртки?
16. Зачем разделять server.py, web_search.py и web_fetch.py?
17. Что делает mcp.run(transport="stdio")?
18. Почему сервер может ничего не выводить после запуска?
19. Почему запуск сервера ещё не подтверждает, что клиент обнаружил инструменты?
20. Что может помешать модели вызвать инструмент?
21. Почему веб-страницам нельзя доверять как инструкциям для модели?
22. Почему этот урок ещё не завершает работу по безопасности?

## 13. Словарь терминов

| Термин | Определение |
|---|---|
| MCP | Протокол взаимодействия модели с внешними инструментами и источниками |
| Сервер | Программа, предоставляющая функции клиентам |
| Клиент | Программа, отправляющая запросы серверу |
| Tool / инструмент | Именованная операция, доступная клиенту и модели |
| SDK | Набор библиотек и средств разработки |
| FastMCP | Высокоуровневый интерфейс MCP SDK для Python |
| Декоратор | Конструкция для регистрации или изменения поведения функции |
| Схема | Формальное описание структуры данных |
| Аннотация типа | Подсказка о типе параметра или результата |
| Transport / транспорт | Способ передачи сообщений |
| stdio | Стандартные потоки ввода и вывода процесса |
| JSON-RPC | Формат сообщений для удалённого вызова процедур |
| Docstring | Строка документации функции или модуля |
| Относительный импорт | Импорт модуля относительно текущего пакета |
| Tool calling | Механизм, через который модель запрашивает выполнение инструмента |
| Валидация | Проверка входных данных на соответствие требованиям |

## 14. Итог урока

В этом уроке мы создали основу MCP-сервера: объект FastMCP, два инструмента с декоратором @mcp.tool(), передачу параметров прикладным функциям и запуск через stdio. Мы разобрали роль аннотаций, описаний инструментов и причину, по которой нельзя использовать stdout для обычной отладки.

Следующий шаг — урок № 11: безопасность и тестирование. Там проверим входные данные, ограничения сетевых запросов, опасные URL и перенаправления, а также подготовим автоматические тесты, которые не зависят от реального интернета.