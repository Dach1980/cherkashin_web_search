# Сборка Windows x64 через GitHub Actions

Этот документ описывает воспроизводимую техническую сборку MCP-сервера. Успешная сборка и CI smoke test ещё не означают, что коммерческий ZIP прошёл пользовательскую проверку в LM Studio.

## Автоматическая сборка

Workflow: [Windows x64 packaged MCP build](../../.github/workflows/windows-build.yml).

Workflow запускается при изменениях в src/, packaging/, requirements.txt и самом workflow, а также вручную через GitHub Actions → Windows x64 packaged MCP build → Run workflow.

Среда сборки:
- GitHub-hosted windows-latest;
- Python 3.11 x64;
- runtime-зависимости из requirements.txt;
- PyInstaller 6.16.0;
- режим PyInstaller onedir --console.

Точка входа — packaging/launcher.py. Ожидаемый исполняемый файл — dist/WebSearchServer/WebSearchServer.exe.

## Проверки в workflow

1. Проверяется наличие EXE.
2. Запускается упакованный EXE как отдельный процесс через официальный MCP stdio client.
3. Выполняется MCP initialize.
4. Проверяется регистрация search_web и fetch_web_page.
5. Вызывается fetch_web_page для https://example.com; проверяется успешный HTTP-ответ.
6. Вызывается search_web; проверяется получение структурированного ответа. Если внешний DuckDuckGo временно недоступен или ограничивает CI, это отдельно отражается в логе и не маскируется под успешный поиск.

Артефакт WebSearchServer-Windows-x64 содержит всю папку dist/WebSearchServer/. Для PyInstaller onedir нельзя копировать только EXE: рядом должны оставаться все созданные библиотеки и ресурсы.

## Как получить артефакт

После успешного workflow:
1. Открой GitHub → Actions → Windows x64 packaged MCP build.
2. Выбери успешный запуск.
3. Внизу страницы скачай WebSearchServer-Windows-x64.
4. Распакуй скачанный artifact ZIP и проверь наличие WebSearchServer/WebSearchServer.exe и соседних файлов.

Артефакт GitHub Actions — промежуточный результат сборки для технической проверки, не готовый коммерческий комплект. Не публиковать его на Boosty до подготовки пользовательских инструкций, шаблона конфигурации, версии, SHA-256 и прохождения чистого теста на Windows с LM Studio GUI.

## Конфигурация LM Studio после получения сборки

После размещения каталога WebSearchServer в постоянной папке укажи фактический абсолютный путь, например:

```json
{
  "mcpServers": {
    "cherkashin-web-search": {
      "command": "D:/ПУТЬ-К-ПАПКЕ/WebSearchServer/WebSearchServer.exe",
      "args": [],
      "env": {}
    }
  }
}
```

Путь выше — шаблон. Его необходимо заменить фактическим путём на компьютере пользователя. Существующие записи в mcpServers сохраняются.

## Что workflow не доказывает

- запуск на всех версиях Windows 10/11;
- совместимость со всеми версиями LM Studio;
- отсутствие предупреждений Microsoft Defender/SmartScreen;
- корректность установки из коммерческого ZIP через Проводник;
- повторное подключение после перезапуска LM Studio;
- работу за корпоративным HTTP(S) proxy;
- постоянную доступность DuckDuckGo.

Эти проверки остаются отдельными release gates.