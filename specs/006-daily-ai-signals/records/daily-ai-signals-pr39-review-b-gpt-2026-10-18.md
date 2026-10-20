# PR #39 — independent review B (gpt), 2026-10-18

Проверен SHA **8f30549a07225b17d1f8a7187b1d4956b174ecb6**, база PR
**d4adc4905d2241f5d311aeb55d3425dd7bb415bb**.
PR: https://github.com/Orlv-85/AI_PARSER/pull/39.
Отдельный detached worktree: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-review-b-gpt`.
Проверка read-only: изменения приложения не вносились, коммитов, push и комментариев в PR нет.
Другие reviewer reports не читались. В основной рабочей папке создан только этот отчёт.

## Выполненные проверки

| Проверка | Результат |
| --- | --- |
| `git fetch origin`, `gh pr view 39`, `gh pr diff 39`; локальный diff указанной базы и SHA; AGENTS, spec, plan, daily-signals, deploy, troubleshooting | Прочитаны требования и изменения в области review B |
| Целевые тесты: `test_web_daily_signals_api.py`, `test_web_public_digest.py`, `test_public_api_write_auth.py`, `test_deepseek_digest.py` | **75 passed**, exit 0 |
| Полный suite один раз, чистый worktree без `.env`, Python 3.14.2, отдельный PostgreSQL 18 | **1140 passed in 53.64s**, без skipped |
| `bash -n scripts/*.sh .codex/skills/multi-agent-orchestration/scripts/*.sh` | exit 0 |
| TestClient с намеренно неполным stored trend | API 200, `/` 500; подтверждение B01 |
| Node VM: выполнение функций из фактического `digest.html`, управляемые ответы fetch | Подтверждение B04; поздний ответ signals другой даты игнорируется; ошибка signals показывает unavailable; escaping работает |
| Chrome: серверный HTML с длинным именем, HTML в vendor, кавычкой в URL; viewport 375×812 и 1280×900 | Ширина документа 375/1280 соответственно, горизонтального overflow нет; одна/три колонки; DOM не содержит внедрённых img/script/onmouseover |
| SQLite: upgrade текущим деревом миграций, downgrade деревом из базы PR | Старое дерево: `Can't locate revision identified by 'b6d1f0a7c3e5'`; текущее дерево: downgrade успешен |
| PostgreSQL: predecessor → `Base.metadata.create_all()` → head → downgrade → head | Успешно; после downgrade сохранены тестовая статья и таблица digest, signals-таблицы удалены |
| Fake docker/flock/timeout: отсутствие timeout и зависание cleanup | Оба сценария оставляют shell ожидающим; внешний test supervisor завершил их; детали B05 |

Для pytest использовался разрешённый launcher, cwd — review-worktree:

```sh
rtk proxy /Users/vyacheslavorlovskiy/.codex/bin/run-pytest \
  --python /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python \
  --env PYTHONPATH=src -- \
  tests/unit/test_web_daily_signals_api.py \
  tests/unit/test_web_public_digest.py \
  tests/unit/test_public_api_write_auth.py \
  tests/unit/test_deepseek_digest.py -q -p no:cacheprovider

rtk proxy /Users/vyacheslavorlovskiy/.codex/bin/run-pytest \
  --python /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python \
  --env PYTHONPATH=src \
  --env AINEWS_TEST_POSTGRES_URL=postgresql+psycopg://review_b:isolated_review_b@127.0.0.1:55447/review_b \
  -- -o addopts= -p no:cacheprovider
```

Указанные credentials относятся исключительно к созданному disposable test container
`ainews-review-b-gpt-pg`, который остановлен после проверки. Существующие локальные БД не использовались.
Provider calls, обращения к production и сетевые записи в GitHub не выполнялись.

## Findings

Номера строк относятся к проверенному SHA, а не к текущей основной рабочей папке.

| ID | Severity | File:line | Дефект | Конкретный сценарий | Evidence | Краткое исправление | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B01 | major | `src/app/web/signals_view.py:75`; `src/app/web/app.py:498` | Допустимый для response model неполный trend обрушает всю страницу digest. | В stored snapshot есть rising/cooling с `current_7d=9`, но отсутствует `expected_7d`; модель подставляет None, форматирование `:g` выбрасывает TypeError, который не входит в обработчик изоляции. | Локально API вернул 200, `/` вернул 500; исключение `TypeError: unsupported format string passed to NoneType.__format__`. | Проверить согласованность полей trend при валидации и безопасно обработать отсутствующее expected; закрыть этот путь в границе изоляции signals и добавить regression test. | confirmed |
| B02 | major | `docs/daily-signals.md:139`; `specs/006-daily-ai-signals/plan.md:970` | Инструкция «revert feature and downgrade» не сохраняет доступ к новой миграции для downgrade. | Оператор возвращает код/образ предыдущего release, затем выполняет указанный downgrade при уже установленной ревизии b6d1f0a7c3e5. Старый образ этой ревизии не содержит. | Реальный Alembic downgrade с migration tree из `d4adc49` завершился `CommandError: Can't locate revision identified by 'b6d1f0a7c3e5'`; с текущим tree прошёл. | Указать точный порядок: остановить writers/app, выполнить downgrade инструментами текущего feature image, затем вернуть старый image/code и запустить сервисы; либо явно оставить аддитивную схему без downgrade. | confirmed |
| B03 | minor | `specs/006-daily-ai-signals/plan.md:639`; `scripts/deploy_prod.sh:238,270` | Описанное восстановление после migration race восстанавливает схему, но не завершает прерванный deploy. | На первом deploy конкурентный `create_all()` приводит к ошибке Alembic; deploy завершается до записи `.last_deploy_image`. Оператор только повторяет `alembic upgrade head`, как советует план. Следующий digest job берёт старый image из receipt, в котором команды daily-signals ещё нет. | `set -e` + миграция на строке 238, запись receipt лишь на 270; job читает receipt на строках 6–7. Саму конкурентную DDL-гонку в данном review не воспроизводил; она явно принята в плане. | После успешной миграции повторить deploy с тем же целевым image до health checks/receipt/scheduler либо документировать эквивалентное завершение deploy. | plausible |
| B04 | minor | `src/app/web/digest.html:490,610,620` | При выборе даты блок signals продолжает показывать предыдущую дату без loading/date marker. | Новый digest уже показан, signals-запрос задержался: под заголовком нового дня видны старые New/Spikes. Если digest-запрос вернул non-2xx, signals нового дня вообще не запрашиваются, старый блок остаётся. | Node VM с исходным JS: после нового digest `previous signals retained=true`; при ошибке digest `signals request dispatched=false`. | Сразу очищать/помечать signals при смене даты, запускать его загрузку независимо от успеха digest; использовать общий request generation guard для согласованности дня. | confirmed |
| B05 | minor | `scripts/run_daily_digest_job.sh:35,43` | Жёсткая граница времени best-effort signals отсутствует без timeout и не распространяется на cleanup. | На PATH нет timeout, а signals зависает в DB/recompute: `--max-seconds` ограничивает dispatch, но не эти операции. Либо timeout отработал, а `docker rm -f` завис. Shell не достигает exit 0, systemd может завершить уже успешно опубликовавший digest job по TimeoutStartSec. | В коде wrapper становится пустым; cleanup вне wrapper. Fake docker со sleep оставляет job ожидающим в обоих случаях, включая сообщение об игнорировании сбоя перед зависшим cleanup. Тест остановлен через 0,5 с; реальное ожидание четырёх часов не выполнялось. | При отсутствии timeout пропускать signals с exit 0 либо обеспечить обязательный эквивалент; cleanup тоже ограничить timeout внутри оставшегося бюджета. | confirmed |

### Уточнения к findings

**B01 — проверка повреждённых данных, а не наблюдавшийся production snapshot.** Нормальный compute
сейчас записывает expected для недельных trends. Но публичная модель явно допускает его отсутствие,
и заявленная изоляция повреждённого signals snapshot нарушается. Минимальная rising-запись:

```json
{"entity_id": 2, "name": "Beam", "type": "model", "today": 4,
 "current_7d": 9, "previous_7d": 3, "publishers": 4, "links": []}
```

В snapshot `status=building_history`, `report_date=2026-10-16` эта запись проходит валидацию.
Другие поля snapshot можно оставить стандартными. Аналогичный путь есть в Cooling.

**B02 — данные digest/weekly не удаляются.** Ошибка именно в последовательности операционных шагов.
Сам downgrade текущей миграции корректен в выполненных SQLite/PostgreSQL проверках.
В инструкции нужно явно закрепить image, которым выполняется downgrade; простого «app/jobs stopped»
недостаточно для доступа к migration code.

**B03 — принятая DDL-гонка не объявляется новым blocker.** Проверка наличия таблицы перед CREATE
не сериализует две транзакции. В PostgreSQL DDL транзакционна; последовательный случай
`create_all → upgrade` исправен. Повтор Alembic может восстановить schema/version, однако не обновляет
release receipt и не выполняет пропущенную часть deploy. Нужно дополнить recovery, не обязательно
менять разрешённый владельцем порядок запуска сервисов.

**B04 — guard внутри loadSignals работает.** Ответ для уже не выбранного дня действительно
игнорируется. Это не устраняет старый DOM во время ожидания. Отсутствие аналогичного guard у
loadDigest существовало до PR; отдельно как новый дефект оно здесь не предъявляется.

**B05 — fallback соответствует тексту плана, но гарантия job result оказывается условной.**
Обычный signals exit 1/124 обрабатывается корректно. Проблема возникает в перечисленных зависаниях;
`--max-seconds` не является общим wall-clock deadline для всего процесса. Проверка с fake Docker
доказывает отсутствие внешней границы, а не частоту такого сбоя в production.

## Production-sensitive changes

1. `web/app.py`, `web/models.py`, `web/signals_view.py`, `web/digest.html`: новый публичный GET,
   чтение snapshot на `/`, response schema, серверный и клиентский renderer, date-change fetch,
   CSS и новые untrusted text/link contexts.
2. `scripts/run_daily_digest_job.sh`: один lock с re-exec, явная единая дата, общий временной бюджет,
   дополнительный container, deterministic container name, timeout/cleanup и сохранение digest exit code.
3. `docker-compose.prod.yml`: ровно одна новая env-строка `AINEWS_DAILY_SIGNALS_ENABLED`, default false.
4. `config/settings.py`: пять новых настроек signals и проверка USD cap; существующие defaults сохранены.
5. `models_sql.py` и миграция `b6d1f0a7c3e5`: шесть новых таблиц, индексы/unique constraints,
   два CASCADE FK к articles; `create_all()` теперь включает эти таблицы во всех существующих вызовах.
6. `storage/legacy_cleanup.py`: расширен allowlist ровно для двух derived CASCADE FK; unknown FK
   по-прежнему запрещает destructive cleanup.
7. Новые CLI/core/storage/ledger modules: платный worker и команды operators, persisted evidence,
   derived reports, локальный ledger и run reports. Подробная корректность compute/resolution — область A;
   здесь проверялись request isolation, runtime budgets, публичные поля и приватность отчётности.
8. README/configuration/deploy/daily-signals/plan: включение флага, backfill, rollout, recovery и rollback.
   Сам deploy script, timers, auth defaults, ports, retention defaults в diff PR не изменены.

## Verified OK

- Auth allowlist добавляет только GET/HEAD для точного signals path. Non-read API methods требуют
  auth; publish bearer token по-прежнему относится только к двум старым POST endpoints. Целевые auth
  tests и полный suite зелёные. GET signals public; admin settings не стал public.
- Snapshot response состоит из reader-facing моделей; extraction provenance, ключи, ledger и
  operator overrides туда не добавлены. Неструктурированные дополнительные поля верхнего уровня
  не пробрасываются response model. Публичные article URLs/event types соответствуют назначению API.
- Имена, vendor, варианты, цитаты, story labels, notes, event labels, title/publisher и URL-атрибуты
  экранируются сервером и JS. Signals links разрешены только при http(s) prefix. В HTML не добавлено
  inline JSON со stored snapshot. Crafted quote/markup не создали исполняемых DOM-узлов/атрибутов.
- Missing/невалидный JSON snapshot возвращает unavailable. SQLAlchemyError из отдельного signals
  read даёт временно недоступный блок при рабочем digest; исключение B01 отдельно выше.
- `_read_daily_signals` читает один report по report_date; есть unique index
  `ix_daily_signal_reports_report_date`. Provider dispatch/recompute не вызываются request path.
  Это не утверждение о единственном SQL на весь endpoint: существующий `create_all()` также
  выполняет schema inspection, а digest имеет собственные запросы.
- Mobile 375 px: cards stack, chips wrap, длинные слова переносятся; desktop 1280 px: три колонки.
  Фактический scrollWidth совпал с viewport в обоих режимах.
- При нормальном завершении Docker: digest failure сохраняет failure и не запускает signals;
  signals failure/timeout сохраняет success и вызывает cleanup. Lock берётся один раз, date разрешается
  один раз до lock, relative path re-exec работает, locked-entry fallbacks совместимы с `set -u`.
- Бюджет обычной timeout-ветки учитывает ожидание lock; максимум signals 2700 s, kill grace 30 s,
  600 s резерв дают запас 570 s до 14400 s unit deadline, если cleanup завершается.
- Детерминированное имя контейнера не сталкивается между обычными job invocations под одним lock.
  При оставшемся stale имени Docker failure попадёт в cleanup; текущий job повторно signals не запускает.
- Compose diff не меняет порты, auth, retention, DB. Флаг false действительно предотвращает новые
  платные runs; изменение `.env` не отменяет уже запущенный процесс с ранее прочитанными settings.
- Последовательные migrations и downgrade исправны; destructive cleanup PostgreSQL tests проходят.
  Ledger использует файл 0600 с fchmod; run JSON записывается через private_write (0600, staged rename),
  вновь создаваемые cache/runs directories — 0700. Run report содержит даты/счётчики/cost/status,
  не article bodies/ключи. Ledger намеренно хранит raw provider responses в приватном файле.
  Web error log пишет тип исключения, а не payload.

## Ограничения проверки и артефакты

- Lint не запускался: это read-only review без code change/commit. Полный pytest запускался один раз.
- UI smoke использовал реальный серверный renderer и Chrome со static local fixture. В static server
  отсутствовали API endpoints, поэтому ожидаемые 404 в console не являются defects PR; утверждения
  «полноценный live backend UI без console errors» не делаю. Асинхронный JS отдельно выполнен в Node VM
  с controlled fetch, HTTP-контракты — через TestClient и tests.
- Одновременная migration/create_all гонка, отказ реального Docker daemon и четырёхчасовой systemd
  timeout не воспроизводились. Последовательные migration recovery и две зависающие shell-ветки
  проверены отдельно. Caddy/production не запускались и не менялись.
- Платные extraction calls не делались. Соответствие качества extraction данным — вне области B.
- Временные воспроизведения: `/private/tmp/pr39-review-b-probe.py`,
  `/private/tmp/pr39-review-b-js.cjs`, `/private/tmp/pr39-review-b-rollback.py`,
  `/private/tmp/pr39-review-b-pg.py`, `/private/tmp/pr39-review-b-shell.py`.
  Они не добавлены в репозиторий; ключевые сценарии и результаты приведены выше, поскольку /tmp временный.
- HTTP server и собственный test PostgreSQL остановлены; viewport override сброшен.
  Review worktree сохранён, tracked worktree status после проверок чистый.

## Verdict

**merge after fixes** — исправить B01 и сделать rollback B02 однозначно выполнимым;
дополнить recovery и обработку UI/job edge cases B03–B05. Зелёный suite не покрывает эти
воспроизведения. Отдельные checkpoint 3/Phase 7 gates, указанные в описании PR, этим review не заменяются.
