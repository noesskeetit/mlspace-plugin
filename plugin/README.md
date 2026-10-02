# MLSpace: MCP и скиллы одним плагином

Для macOS и Linux, включая SSH:

```bash
uvx mlspace-plugin@latest setup
```

Мастер принимает два ключа, предлагает поиск и выбор workspace, добавляет
marketplace этого репозитория и устанавливает `mlspace@mlspace` в Claude Code
или Codex. В OpenCode подключает MCP напрямую и устанавливает скиллы в его
собственный каталог. Затем проверяет скиллы и запуск MCP.

Откройте новую сессию клиента. Самостоятельно запускать сервер не требуется.
Подробнее: [установка](../INSTALL.md), [инструкция агенту](../INSTALL_AGENT.md).

## Состав

- 12 скиллов в `skills/`;
- манифесты Agent Plugins, Claude Code и Codex;
- команда MCP `uvx --from mlspace-plugin==<версия> mlspace-plugin --transport stdio`.

Версия сервера из PyPI совпадает с версией плагина. ZIP релиза содержит каталог
`plugin/`, marketplace-манифесты, README, LICENSE и SHA256SUMS. Вложенного wheel
нет: для запуска нужен доступ к PyPI. Исходники скиллов находятся в одном месте —
`plugin/skills`; их копиями в кеше управляют нативные клиенты.

Ключи, CA и указатель на credentials находятся вне кеша плагина. Изменение
`XDG_CONFIG_HOME` при запуске клиента не теряет выбранный файл настроек.

## Повторная установка и обновление

```bash
uvx mlspace-plugin@latest setup --force
```

Обновляются сохранившиеся подключения мастера. Уже установленная целевая версия
не переустанавливается. Собственного фонового обновления нет; политики клиентов
мастер не меняет. Не редактируйте нативный кеш плагина: обновление заменяет его.

## Ручная диагностика нативных клиентов

Обычно эти команды не нужны — их выполняет setup. Для проверки состояния:

```bash
claude plugin marketplace list --json
claude plugin list --json
codex plugin marketplace list --json
codex plugin list --json
```

Marketplace `mlspace` должен ссылаться на
`https://github.com/noesskeetit/mlspace-plugin.git`, а плагин `mlspace@mlspace`
должен быть включён. Если CLI не поддерживает команды plugin, обновите клиент.
Прямая MCP-регистрация с тем же именем может конфликтовать с нативным плагином;
мастер сообщает об этом до ввода ключей и не удаляет пользовательский конфиг.

## Сборка

```bash
uv run python scripts/gen_plugin.py --check
uv build
uv run python scripts/build_plugin.py
```

ZIP появится в `dist/plugins/`. Генератор проверяет манифесты плагина и оба
marketplace-манифеста в корне репозитория. Порядок публикации — в [RELEASE.md](../RELEASE.md).
