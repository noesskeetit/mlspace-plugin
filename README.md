# mlspace-plugin

**Установка:** [инструкция человеку](https://github.com/noesskeetit/mlspace-plugin/blob/main/INSTALL.md) · [инструкция агенту](https://github.com/noesskeetit/mlspace-plugin/blob/main/INSTALL_AGENT.md).
Агенту, получившему ссылку на репозиторий для установки: сначала прочитайте INSTALL_AGENT.md.

MCP-сервер для **публичного API Cloud.ru MLSpace v2** (`https://api.ai.cloud.ru/public/v2`).

Открывает операции MLSpace, не помеченные `deprecated` в поставляемой схеме OpenAPI, — обучение, инференс,
ноутбуки, TensorBoard'ы, воркспейсы, аллокации, очереди, Docker Registry,
перенос данных и каталог ресурсов — LLM-агентам в виде **17
инструментов**, каждый с параметром `action`. Под капотом — 126 операций,
описанных в поставляемой схеме OpenAPI и сгруппированных для работы LLM-агента.

> Одна учётная запись, несколько выбранных workspace; stdio и локальный streamable-HTTP. Запись доступна по
> умолчанию; необратимые действия — за гейтом `confirm=true`.

---

## Что это и зачем

MLSpace отдаёт большой REST-API (142 пути, 185 операций в OpenAPI v2.8.1). Дёргать
его «голым» из LLM-агента неудобно: разнобой в пагинации, статусах, версиях путей,
часть параметров обязательны только в рантайме и т.п. Этот сервер прячет всю
механику (аутентификация, заголовки, шаблоны путей, кодирование query, тела
запросов, обработка ошибок) и выставляет наружу компактный, предсказуемый,
дружелюбный к модели интерфейс:

- **17 инструментов вместо 185 «тонких»** — модель не тонет в списке тулов; каждый
  инструмент = один домен, конкретное действие выбирается через `action`.
  (Автогенерация по спеке дала бы 185 инструментов с именами по 66 символов вида
  `create_notebook_workspace_autoshutdown_rule_v2_public_v2_notebooks_v2_…`.)
- **Подсказки прямо в описании** — для каждого `action` указаны обязательные
  параметры и форма тела (required/optional/enum-поля), вытянутые из спеки.
- **Ступени защиты** — гейт `confirm=true` на необратимые операции, dry-run для
  проверки write-запроса без отправки, режим read-only для наблюдательных сценариев.
- **Чистый контекст** — компактный JSON, обрезка длинных списков и логов, удаление
  k8s-шума, редактирование секретов в ответах.

---

## Установка и настройка

Python 3.10+, macOS или Linux. Установка из PyPI:

```bash
uvx mlspace-plugin@latest setup
```

Из каталога скачанного репозитория:

```bash
uv tool install .
mlspace-plugin setup
```

Мастер обнаруживает Claude Code, Codex и OpenCode, просит только Key ID и Key Secret
с маской `*****`, предлагает поиск воркспейсов по имени/проекту/ID и множественный
выбор. Проверяет API, сохраняет credentials в пользовательский `.env` с правами
`0600`. Для Claude Code и Codex мастер добавляет marketplace этого репозитория
и устанавливает нативный плагин с MCP и скиллами. OpenCode получает MCP и скиллы
в собственном каталоге. Мастер проверяет запуск MCP; затем откройте новую сессию
клиента — сервер запускается автоматически.

TLS использует системные доверенные CA. Для корпоративного PEM есть `--ca-file`:
мастер сохраняет копию для последующих запусков. Ошибка TLS/сети останавливает
настройку без перезаписи прежнего файла и без запроса ручного x-api-key.

Повторная настройка — `uvx mlspace-plugin@latest setup --force`: сохранённые ключи на прежнем
endpoint переиспользуются. Для замены ключей добавьте `--replace-credentials`.
Для stage укажите `--base-url https://mlspace-stage.example.com`.
Только credentials без подключения клиентов — `--config-only`.
Уже установленный нативный плагин из этого репозитория переиспользуется.

Подробнее: [установка, SSH, сертификаты и повторная настройка](https://github.com/noesskeetit/mlspace-plugin/blob/main/INSTALL.md).
Для разработки: `uv sync --extra dev` и `uv run pytest`.

**Порядок поиска кредов** — от общего к частному, побеждает более конкретное:

1. Файл, сохранённый `setup` (по умолчанию `~/.config/mlspace-plugin/.env`)
2. файл из `MLSPACE_ENV_FILE` — выбран явно
3. настоящие переменные окружения — бьют любой файл

Файл `.env` из текущего каталога автоматически не читается. Для разработки
укажите его явно через `MLSPACE_ENV_FILE`, чтобы чужой репозиторий не мог
подменить адрес API при использовании сохранённых ключей.

`~/.config/mlspace-plugin/credentials-path.json` хранит только путь к выбранному
файлу: настройка через `--path` или `XDG_CONFIG_HOME` работает и после перезапуска
клиента с другим окружением. Повреждённый указатель или отсутствующий целевой файл
дают ошибку; другой аккаунт молча не подставляется.

| Переменная | Обяз. | По умолчанию | Назначение |
|---|:---:|---|---|
| `MLSPACE_CLIENT_ID` | ✅ | — | Cloud.ru Key ID (личный или сервисного аккаунта) |
| `MLSPACE_CLIENT_SECRET` | ✅ | — | Cloud.ru Key Secret |
| `MLSPACE_API_KEY` | | — | `x-api-key` одного воркспейса; без него сервер получает ключ сам |
| `MLSPACE_WORKSPACE_ID` | Для legacy singleton | — | ID единственного воркспейса |
| `MLSPACE_WORKSPACES` | Вместо legacy пары | `[]` | Сохранённый JSON-каталог выбранных workspace: `id`, `name`, `project_name`, опциональный `api_key`; пишет мастер |
| `MLSPACE_ENV_FILE` | | — | Явный путь к файлу с кредами; имеет приоритет над пользовательским конфигом |
| `MLSPACE_CA_FILE` | | системные CA | Дополнительный доверенный PEM; setup сохраняет копию |
| `MLSPACE_BASE_URL` | | `https://api.ai.cloud.ru` | Хост API |
| `MLSPACE_READONLY` | | `false` | `true` убирает все 58 write-действий из перечня `action` |
| `MLSPACE_DRY_RUN` | | `false` | Валидировать write, но не отправлять (вернуть превью) |
| `MLSPACE_TRANSPORT` | | `streamable-http` | `streamable-http` или `stdio` |
| `MLSPACE_HOST` / `MLSPACE_PORT` | | `127.0.0.1` / `8000` | Привязка HTTP (только loopback) |
| `MLSPACE_ENABLED_DOMAINS` | | _(все)_ | Список через запятую — ограничить набор инструментов |
| `MLSPACE_TIMEOUT` | | `60` | Таймаут запроса, сек |
| `MLSPACE_NAMESPACE` | | _(из workspace_id)_ | Закрепить k8s-namespace воркспейса; пусто = резолвится автоматически |
| `MLSPACE_LIST_DEFAULT_LIMIT` / `MLSPACE_LIST_MAX_LIMIT` | | `50` / `200` | Размер списков по умолчанию / максимум |
| `MLSPACE_LOG_TAIL_LINES` | | `200` | Сколько последних строк лога показывать |

Обмен `service_auth` (токен с TTL 1ч) выполняется внутри — это не инструмент.

## Подключённые воркспейсы и адресация

`mlspace_contexts` возвращает сохранённый набор, endpoint и окружение без секретов
и сетевого обхода. Один, три или десять воркспейсов равноправны: основного/текущего
нет. `mlspace_workspaces list` показывает доступность учётных данных и не расширяет
набор. Legacy-конфигурация остаётся одним подключением.

Адресные действия принимают `target` (ID или однозначное название) и, для найденных
jobs/notebooks, `resource_ref`. Ссылка содержит окружение, workspace, тип и адрес
объекта; конфликтующие аргументы отклоняются. Диагностика и перезапуск сохраняют
адрес выбранного объекта, а успешный перезапуск получает новую ссылку, когда API
вернул распознаваемое новое имя. Контекст запроса не доказывает владельца общей очереди.
При одном workspace выбор не нужен. Явная работа в A сохраняет A для её шагов, а
отдельное чтение B этого не меняет. Общий запрос «теперь покажи задачи» снова охватывает
подключённый набор. Делегированное «в любом из A/B с подходящим GPU» позволяет выбрать
место по проверенным условиям без повторного вопроса; реальная неоднозначность требует
уточнения. Образец ноутбука сам по себе не определяет место создания.

| Read-only helper | Параметры и результат |
|---|---|
| `mlspace_jobs_overview` | `targets`, `author`, `status`; динамически обнаруживает MT-регионы и читает страницы jobs |
| `mlspace_notebooks_overview` | `targets`; читает страницы notebooks, включая paused |
| `mlspace_queue_inspect` | `queue_id`, `target` исходной очереди, `candidate_nodes`, `targets` областей наблюдения; проверяет доступные jobs/notebooks/pods, все приоритеты pending и факты/нагрузку узлов |

У helpers общий набор бюджетов: `page_size=100`, `max_pages=50` на поток,
`max_requests=200` на логические inventory GET, `max_items=200` на вывод.
Авторизация, получение ключа и возможный 401 retry — дополнительные транспортные
запросы. `targets` по умолчанию — весь выбранный набор; эти helpers доступны при
включённом соответствующем домене. Фильтра `region` у jobs overview нет: для узкого
регионального чтения доступен `mlspace_jobs list` с пагинацией.

Ответ показывает `requested_scope`, `checked_scope`, `failures`, `observed_at` и
полноту; строки `items` содержат `source` (тип наблюдения), `data`, `provenance` и
при распознанном адресе `resource_ref`. `complete` требует успешного полного чтения
и отсутствия усечения вывода. `observed_count` — число наблюдений, не полный итог
при частичном чтении и не сумма уникальной общей мощности. Частичный поиск не
доказывает уникальность имени; «все» после сокращённого списка требует понятного
множества. Явный фильтр `author` можно повторно использовать как настройку пользователя,
но он не доказывает identity: задачи коллег нельзя называть «моими» по членству в workspace.

Перед переносом вычислительного узла используйте `transfer_compute_node`: сначала
`mlspace_queue_inspect`, затем при запросе на выполнение `mlspace_queues add_nodes`
в целевую очередь с `{nodes, force_withdrawal:false}`. Узел отличается от Jupyter
сервера. Настройки GPU у paused notebook не означают занятую мощность; pending —
ожидающая потребность, а не работающая нагрузка. Даже полное чтение не гарантирует
видимость всех чужих workload общей аллокации: `cross_workspace_coverage` остаётся
`unknown`. Не обещайте перенос без влияния по такому обзору. Существующие правила
подтверждения операций сохраняются; отдельного подтверждения workspace нет.

---

## Запуск

```bash
mlspace-plugin                          # streamable HTTP на 127.0.0.1:8000
MLSPACE_TRANSPORT=stdio mlspace-plugin  # stdio
```

### Подключение из MCP-клиента

**Streamable HTTP** (по умолчанию): запустите `mlspace-plugin`, направьте клиента на
`http://127.0.0.1:8000/mcp`.

**stdio** (Claude Desktop / Cursor / Codex) — пример для `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mlspace": {
      "command": "mlspace-plugin",
      "env": {
        "MLSPACE_TRANSPORT": "stdio",
        "MLSPACE_ENV_FILE": "/absolute/path/to/mlspace-plugin/.env"
      }
    }
  }
}
```

---

## Инструменты

Каждый инструмент принимает `action` + параметры этого действия. Полный список
действий с подсказками по телу виден в описании инструмента у клиента. `[w]` —
write-операция (скрыта из `action`-перечня при `MLSPACE_READONLY=true`).

| Инструмент | Назначение | Действия |
|---|---|---|
| `mlspace_jobs` | Задачи обучения | list, get, logs, list_nodes, list_pods, get_params, get_preemptors, run`[w]`, restart`[w]`, delete`[w]` |
| `mlspace_build_image` | Сборка кастомных образов | list, run`[w]`, get, get_logs, get_pods, delete`[w]` |
| `mlspace_notebooks` | Jupyter-серверы | list, get, autoshutdown_get, create`[w]`, delete`[w]`, users_list, users_set`[w]`, users_revoke`[w]`, pause`[w]`, resume`[w]`, modify`[w]`, autoshutdown_set`[w]`, autoshutdown_delete`[w]` |
| `mlspace_tensorboards` | TensorBoard-инстансы | list, get, create`[w]`, modify`[w]`, pause`[w]`, resume`[w]`, delete`[w]` |
| `mlspace_inference` | Сервисы инференса | list, get, predict, create`[w]`, update`[w]`, delete`[w]` |
| `mlspace_async_inference` | Асинхронный инференс | list, predict, get_result, get_status |
| `mlspace_dalle` | DALL-E (async) | predict, result |
| `mlspace_workspaces` | Воркспейсы | get_api_key, status, users, list, get, allocations, allocation_queues |
| `mlspace_allocations` | Аллокации ресурсов | list, list_defaults, get, list_assignments, list_instance_types, get_nodes, set_default`[w]`, unset_default`[w]` |
| `mlspace_queues` | Очереди аллокаций / shared-кластер | list, get, defaults, instance_types, jobs, notebooks, pods, awaiting_launch_resources, queue_defaults, assign_workspace`[w]`, delete`[w]`, create`[w]`, update`[w]`, assign`[w]`, unassign`[w]`, set_default`[w]`, unset_default`[w]`, add_nodes`[w]`, assign_shared`[w]`, unassign_shared`[w]` |
| `mlspace_docker_registry` | Docker Registry | current_registry, list_repos, get_repo, update_repo`[w]`, delete_repos`[w]`, repo_fav`[w]`, list_images, get_image, delete_images`[w]`, list_tags, create_tag`[w]`, update_tag`[w]`, delete_tags`[w]`, generate_password`[w]` |
| `mlspace_data_transfer` | Коннекторы / переносы / история | list_connectors, get_connector, create_connector`[w]`, update_connector`[w]`, fav_connector`[w]`, halt_connector`[w]`, try_connector`[w]`, get_connector_logs, delete_connectors`[w]`, list_sources, list_transfers, get_transfer, create_transfer`[w]`, update_transfer`[w]`, fav_transfer`[w]`, switch_transfer`[w]`, delete_transfers`[w]`, list_history, get_history_status, get_event_logs, cancel_history`[w]`, rerun_history`[w]`, fav_history`[w]`, delete_history`[w]` |
| `mlspace_resources` | Каталог вычислений | configs, instance_types, nodes, nodes_load, rate_limits |

Волатильные значения (`region`, статус задачи, `connector_type`, …) — это обычные
строки, не фиксированные enum'ы: их известные значения перечислены в описании
параметра, но новые значения, которые API добавит позже, тоже принимаются. Тела
write-запросов подаются параметром `body: dict`; обязательные/вложенные/enum-поля
вынесены в описание действия. Локальная валидация тела (`lint`) **fail-open** —
ловит только явные структурные ошибки (нет обязательного поля, явное несовпадение
типа) до похода в сеть и никогда не отклонит тело, которое API бы принял.

---

## Плагин: Codex, Claude Code и совместимые агенты

[Поставка MLSpace](plugin/README.md) объединяет MCP-сервер и 12 скиллов.
Обычная установка — `uvx mlspace-plugin@latest setup`: marketplace подключается
автоматически. Нативные клиенты управляют плагином `mlspace@mlspace` сами.
Манифест фиксирует точную версию runtime из PyPI вместе со скиллами.
Ключи и CA остаются в пользовательском конфиге вне кеша плагина.

Повторный `setup --force` обновляет сохранившиеся подключения мастера.
Собственного фонового обновления нет; политики автообновления клиентов мастер
не меняет. ZIP релиза содержит те же манифесты и скиллы, без вложенного wheel.

Для других агентов предусмотрены Agent Plugins 1.0, Agent Skills и обычное
MCP-подключение; поддержку конкретного загрузчика нужно проверять отдельно.
Пошаговые сценарии поставляются только скиллами плагина; сервер отдаёт общие правила
в instructions. Ключевые правила подачи ответа также включены в описания инструментов
для клиентов, которые не передают модели instructions сервера.
`tests/test_skills.py` сверяет скиллы с реальными инструментами.

---

## Безопасность

- **Гейт подтверждения**: 16 необратимых действий (удаления, отзыв доступа,
  отмена переноса, ротация пароля реестра) требуют `confirm=true`.
- **Смена пароля Registry выключена по умолчанию**, поскольку затрагивает личный
  аккаунт и уже работающие подключения. После согласования ротации оператор может
  задать `MLSPACE_ALLOW_REGISTRY_PASSWORD_ROTATION=true` в конфигурации сервера и
  перезапустить MCP. `setup` не включает этот параметр. После операции выключите его
  и снова перезапустите MCP. Флаг инструмента `confirm=true` не обходит этот запрет.
- **Режим read-only** (`MLSPACE_READONLY=true`): все 58 write-действий исчезают
  из `action`-перечня — модель их не видит — и блокируются в рантайме как
  страховка. По умолчанию **выключен**: сервер задуман как рабочий инструмент, а
  не смотровое окно. Включайте для наблюдательных сценариев, общих стендов и
  всего, где агенту незачем ничего менять.
- **Dry-run** (`MLSPACE_DRY_RUN=true`): write-запрос полностью валидируется (lint
  тела, шаблон пути, гейт confirm), но **не отправляется** — возвращается превью
  запроса, который ушёл бы в API. Удобно дать модели собрать и проверить write
  до реального применения.
- **Снос воркспейса не выставлен**: `POST/DELETE /workspaces/v3/` (bootstrap /
  debootstrap) намеренно не реализованы — слишком большой радиус поражения для
  общего сервера. Жизненный цикл воркспейса — только через консоль.
- **Сеть**: HTTP-транспорт отказывается слушать не-loopback адрес (в v1 нет
  серверной аутентификации).
- **Секреты в ответах** (пароль Registry, API key воркспейса) по умолчанию
  маскируются. Для задачи, которой нужно реальное значение, действия
  `mlspace_docker_registry(action="generate_password")` и
  `mlspace_workspaces(action="get_api_key")` принимают `reveal_secret=true`
  вместе с `confirm=true`. Это раскрывает секрет в результате инструмента:
  он становится доступен модели и может сохраниться в истории MCP-клиента.
  Флаг действует только на эти операции, а не отключает маскирование глобально.
  `generate_password` меняет пароль; агент должен получить разрешение на ротацию
  и передать `reveal_secret=true` сразу, если новый пароль нужен для `docker login`.
  Для входа используйте `--password-stdin`; не помещайте пароль в обычный ответ,
  документацию или репозиторий. Обычным MCP-запросам ручное получение ключа не нужно.

> Важно про `confirm`: этот флаг ставит **сам агент** в том же вызове. Это защита от
> случайного действия, а **не** human-in-the-loop. Подтверждение человеком обеспечивает
> клиент, если в нём настроено согласование операций; `destructiveHint` — лишь подсказка.
> `reveal_secret` также является явным запросом агента, а не отдельным окном согласия.
> `MLSPACE_READONLY=true` блокирует изменения, включая ротацию пароля, но не чтение
> workspace API key с явным раскрытием. Это не режим запрета экспорта секретов.
> Агент с доступом к изменению конфигурации сервера способен изменить и его ограничения;
> настройки MCP не заменяют права доступа в API и клиенте. После явного раскрытия секрета
> сервер не может гарантировать, что модель не повторит его в своём ответе.

---

## Разработка

```bash
pytest          # юнит- + drift/контракт-тесты (моки HTTP, живые креды не нужны)
ruff check .
mypy src
```

Сервер сверяется с небольшим сгенерированным артефактом
(`src/mlspace_mcp/spec/body_schemas.json`) ради подсказок по телу запроса и
мягкого lint'а; полный `openapi.json` нужен только для сборки/тестов.

### Обновление спеки (после смены версии API)

1. Перевыкачать `src/mlspace_mcp/spec/openapi.json` с OpenAPI-эндпоинта MLSpace.
2. Перегенерировать схемы тел: `python scripts/gen_body_schemas.py`.
3. Прогнать `pytest` — drift/контракт-тест поймает любое действие, чьё
   `(method, path)` исчезло или стало deprecated; поправить соответствующий
   `tools/<domain>.py`.

### После правки скилла

Правьте `plugin/skills/<name>/SKILL.md` и запустите `pytest tests/test_skills.py`.
После смены версии пакета — `python scripts/gen_plugin.py` для манифестов.

---

## Архитектура

```
LLM ⇄ FastMCP (streamable-HTTP/stdio) ⇄ tools/<domain>.py (зонтичные тулы)
        ⇄ MLSpaceClient ⇄ TokenManager ⇄ api.ai.cloud.ru/public/v2
```

| Модуль | Ответственность |
|---|---|
| `config.py` | Настройки (`Settings`) из окружения: креды, base_url, readonly, dry_run, транспорт, host/port, таймаут, включённые домены. |
| `auth.py` | `TokenManager`: обмен `service_auth`, кэш токена (TTL 1ч), single-flight рефреш за ~60с до истечения и при 401. |
| `client.py` | `MLSpaceClient`: единый `httpx.AsyncClient`, инъекция заголовков, шаблоны путей, повторяемые query-ключи, JSON-тело на любом методе (включая DELETE), один прозрачный ретрай на 401. |
| `errors.py` | Маппинг HTTP/исключений → понятные сообщения (включая разбор `detail[]`). |
| `formatting.py` | Компактный JSON, обрезка списков/логов, удаление шумовых ключей, редактирование секретов. |
| `workspace_context.py` / `resource_refs.py` | Выбор фиксированного контекста, отдельные клиенты и проверяемые адреса jobs/notebooks. |
| `overview.py` | Ограниченный обход инвентаря и очереди с происхождением и полнотой наблюдений. |
| `job_hooks.py` | Job preflight, fail-closed delete guard и совместимость ответов; leaf без импорта registry. |
| `registry.py` | `Op`/`Param`/`DomainTool` + единый дженерик-диспетчер: стрип write в readonly, гейт `confirm`, dry-run, clamp пагинации, lint тела, формат ответа. |
| `tools/<domain>.py` | Чистые декларативные данные: `DOMAIN: DomainTool` (карта `action → Op` + список `Param`). Никакой механики запросов. |
| `bodyspec.py` | Загрузка `body_schemas.json`; `summarize()` для подсказок + fail-open `lint()`. |
| `server.py` / `__main__.py` | Сборка `FastMCP`, общие instructions, регистрация доменов, запуск транспорта. |

Каждый доменный модуль — независимая единица из чистых данных; вся механика живёт
в ядре один раз, поэтому домены не могут «разъехаться» по заголовкам/путям/
кодированию.

---

## Документация

- [Установка плагина с MCP и скиллами](plugin/README.md).

## Обратная связь и вклад в проект

Нашли ошибку или неудобный сценарий работы с MLSpace? Создайте [Issue](https://github.com/noesskeetit/mlspace-plugin/issues): опишите, что хотели сделать, что получилось, версию плагина,
ОС и клиент — Claude Code, Codex или OpenCode. Не прикладывайте ключи, токены,
`.env` или логи с чувствительными данными.

Исправления и улучшения присылайте через [Pull Request](https://github.com/noesskeetit/mlspace-plugin/pulls).
Как запустить проверки и устроен проект — в [CONTRIBUTING.md](https://github.com/noesskeetit/mlspace-plugin/blob/main/CONTRIBUTING.md).

**Особенно рады вашим скиллам!** Если вы нашли удобный способ запускать обучение,
разбирать ошибки, работать с данными или обслуживать инференс — оформите его
в скилл и поделитесь. Такие сценарии помогают всем проще работать с MLSpace.
Готовая реализация необязательна: можно начать с Issue с примером задачи и
ожидаемым результатом.
