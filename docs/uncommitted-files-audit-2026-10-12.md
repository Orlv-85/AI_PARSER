# Аудит незакоммиченных файлов — 2026-10-12

## Согласованное выполнение

После аудита пользователь разрешил конкретный план: сохранить правило AGENTS,
закоммитить отчёты и полезную историю с архивными пометками, исправить поисковый
промпт и удалить старый export/локальные permissions. Незавершённые weekly
script/test и scheduled prompt остаются на месте. Private caches/journals/backups
сохраняются. Production и обработка статей не входят в реализацию.

Одобрены **три коммита**, заменяющие семь предложенных ниже:
1. Правило AGENTS.md.
2. Архив, отчёты и задание/результат аудита.
3. Актуальный поисковый промпт и итог локальной очистки.

История перенесена в `docs/archive/2026-10-10-12/` с исходной структурой путей.
Markdown-файлы имеют архивный баннер; JSON contexts — `archive_metadata`.
Архивный README указывает конечные outcomes и запрет использовать прежние
commands/head/approvals как актуальный handoff. Ссылки Markdown пересчитаны.
Поисковый промпт перемещён в `docs/prompt-search-new-sources-2026-10-10.md`,
использует текущий `sources.yaml`, YAML defaults и явно local-only scope.
`sources.existing.json` и `.codex/rules/operations.rules` удалены локально.
Оба файла были untracked: их удаление не создаёт Git deletion diff и фиксируется
здесь как разрешённая локальная операция. Удаление operations.rules убирает
содержащиеся в этом файле allow-правила, а не все отдельно сохранённые разрешения.

Обязательные проверки выполнены до коммитов:
- `make lint PYTHON=./venv1/bin/python`: ruff/mypy passed, pylint 10.00/10.
- Полный `./venv1/bin/pytest --cov=app --cov-report=term --cov-fail-under=90`:
  **854 passed, 0 skipped, coverage 91.38%**, 101 warnings, 34.96 s.
  Использована чистая локальная копия текущих tracked файлов и сохранённой
  weekly-пары, без `.env`; отдельная файловая SQLite и новый PostgreSQL 18
  container только для этой задачи. Production БД и ранее существовавшие
  тестовые контейнеры не использовались. Предупреждения тестов не исправлялись
  попутным изменением приложения.
- Проверены 48 относительных Markdown-ссылок архива; broken links нет.
- Архивные JSON корректны; исходные payloads сохранены. Markdown body сохранён
  за исключением баннера и пересчитанных ссылок. SHA-256 трёх незавершённых
  файлов совпадают с исходным аудитом; они не включаются в staging.

PR оформляется из отдельной ветки
`chore/archive-local-session-materials-2026-10-12` на `master`.
Разделы ниже сохраняют исходный аудит и прежние предложения; актуальное
разрешение пользователя и результат реализации приведены в этом разделе.

## Решение и границы

Это аудит и конкретный план, а не выполненная очистка. Создан только этот отчёт. Исходные файлы не переписаны, не перемещены и не удалены; staging, commit, push, clean, reset и restore не выполнялись. Production, hold-разбор, fetch, weekly и платные модели не запускались.

В ходе аудита пользователь уточнил варианты: **коммитить или удалить**, но **незавершённую работу сохранить**. Поэтому итоговые действия:
- **Закоммитить: 20 файлов**, включая этот отчёт. Исторические документы предварительно оформить как архив в Git; это часть подготовки коммита, а не отдельное неопределённое «оставить».
- **Удалить: 2 файла**, с условиями ниже.
- **Оставить до завершения: 3 файла** — связанная пара weekly-preview/test и действующий промпт следующей scheduled-проверки.
- Ignored private cache, payment/provider journals, backups и operational receipts не входят в эти 25 файлов. Они сохраняются и не попадают в Git.

Первоначальный вариант с отдельной категорией «архивировать локально» заменён этим планом после уточнения пользователя. Всё ниже — рекомендации, ожидающие согласования; незавершённое нельзя удалять для получения чистого git status.

## Проверенное состояние Git и отсутствие наблюдаемого дрейфа

Рабочая ветка: `master`. Локальный HEAD и `origin/master`:
`56e0f4c497f8d7672e1e87c22e073dcf31d8c7bc`.
Origin: `https://github.com/Orlv-85/AI_PARSER.git`.
Живой `git ls-remote` подтвердил тот же SHA для удалённого master и тега `v0.1.85`; stale remote-tracking ref не использован как единственное доказательство. Fetch не потребовался.

На старте: **1 modified, 0 staged, 23 untracked**. Все 24 исходных файла перечислены в таблице. После создания отчёта ожидаются 1 modified и 24 untracked.

GitHub PR API подтвердил:
- [#21](https://github.com/Orlv-85/AI_PARSER/pull/21): merged 2026-10-12 06:15:42 UTC, merge `56e0f4c`, локальный тег `v0.1.85`.
- [#20](https://github.com/Orlv-85/AI_PARSER/pull/20): merged 06:06:34 UTC, merge `2989b24`, тег `v0.1.84`.
- [#19](https://github.com/Orlv-85/AI_PARSER/pull/19): merge `6d6ea78`, итоговый daily-report.
- [#16](https://github.com/Orlv-85/AI_PARSER/pull/16): merge `a7cbb25`, implementation `4e46089`, re-enrichment и даты.
- [#15](https://github.com/Orlv-85/AI_PARSER/pull/15): merge `d1bc3fc`, implementation `c787ce0`, cleanup и retention 800.
- [#14](https://github.com/Orlv-85/AI_PARSER/pull/14): merge `ef7eb3f`, implementation `30e3eb4`, production screening/weekly-off.
- [#13](https://github.com/Orlv-85/AI_PARSER/pull/13): merge `834c48d`, final head `dece005`, semantic admission и два исправления ревью.
- [#9](https://github.com/Orlv-85/AI_PARSER/pull/9): merge `31b9823`, implementation `5e67a05`, source registry repair.

Все перечисленные implementation-коммиты проверены как предки актуального `origin/master`. В локальных ветках сохранились `feat/weekly-historical-preview` на `c56a1c8`, `backup/master-before-sync-2026-10-11`, feature/fix-ветки и другие worktree. Их очистка вне задания.

Процессы Codex с PID 2404, 82814 и 80632 имеют cwd этого репозитория. Само наличие процесса не доказывает запись. По `lsof` у них не обнаружено открытых на запись дескрипторов проверяемых файлов. Повторная проверка 06:36:32 UTC показала совпадение SHA-256, mtime и статусов всех 24 файлов со стартом. Контрольные суммы приведены ниже; перед реализацией плана их нужно повторно сравнить.

Это наблюдение стабильного снимка, а не эксклюзивная блокировка других сессий. Не следует утверждать, что других сессий нет. При новом дрейфе реализацию соответствующей группы остановить и перечитать изменившийся файл.

Финальная проверка 06:43:37 UTC: SHA-256 всех 24 исходных файлов совпадают; единственный новый путь — этот отчёт; staged paths отсутствуют. После этой проверки вносилось только данное уточнение в сам отчёт.

## Таблица решений по каждому файлу

`M` — modified в рабочем дереве, `??` — untracked; индекс пуст. «Закоммитить после оформления» не означает, что файл уже готов к staging без указанных правок.

| Путь | Статус | Назначение | Действие | Конкретное основание и подготовка |
|---|---|---|---|---|
| `AGENTS.md` | M | Постоянное правило пользователя о handoff-промптах | **Закоммитить** | Diff содержит только новый раздел Prompts For Other Sessions, 7 добавленных строк. Полезное намеренное правило отсутствует в origin/master; сохранить дословно. |
| `.codex/rules/operations.rules` | ?? | Локальные allow-правила для команд | **Удалить** | Не код приложения и не общая инструкция проекта: разрешения commit/tag/push, PostgreSQL lifecycle с любым путём/портом и привязка к отсутствующему `/private/tmp/ai-news-server-ops-20261004.py reports`. Нет ссылок из tracked-файлов и нет аналога в истории Git. Удаление затрагивает удобство локальных разрешений; не использовать этот файл как репозиторную политику. Иные сохранённые разрешения Codex этим аудитом не проверялись и не меняются. |
| `docs/daily-cycle-verification-results-2026-10-12.md` | ?? | Новый фактический результат daily-цикла и PR #20/#21 | **Закоммитить** | Дополняет tracked `docs/daily-publication-results-2026-10-11.md`: scheduled failure, manual resume, два исправленных Cognition date, scope 48/7/41 и 11/1/10, v0.1.85. Аналога этих итогов в origin/master нет. Проверки/production facts оформить как исторические receipts указанного времени, не как проверки этого аудита. |
| `docs/pr-13-review-2026-10-10.md` | ?? | Первое и повторное ревью semantic admission | **Закоммитить после оформления** | Оба замечания исправлены в `dece005`, что видно в коде и PR #13. Unique value: независимые воспроизведения и границы проверки. Сохранить как завершённое ревью в архиве Git; нижнее задание агенту относится к старому head. |
| `docs/prompt-audit-uncommitted-files-2026-10-12.md` | ?? | Исходное задание этого аудита | **Закоммитить** | Связывает план с авторизованным scope и требованием сохранить paid/private artifacts. Отдельно указать в отчёте последующие уточнения пользователя; сам исходный промпт не переписывать. |
| `docs/prompt-cleanup-legacy-articles-jev-2026-10-11.md` | ?? | Требования к завершённой legacy cleanup | **Закоммитить после оформления** | Implementation `c787ce0`/PR #15 и tracked `docs/legacy-articles-jev-cleanup.md`, `docs/legacy-articles-jev-cleanup-2026-10-11.md` — конкретные выполненные аналоги. Промпт сохраняет исходный scope/ограничения, не является копией отчёта; архивировать в Git с completed/superseded status. |
| `docs/prompt-fix-daily-publication-2026-10-11.md` | ?? | Исходный scope UTC scheduling/grounded publication | **Закоммитить после оформления** | Механизм и manual publication доставлены PR #17–#19; tracked `docs/daily-publication-results-2026-10-11.md` фиксирует outcome, новый report 12 октября — scheduled failure. Сохранить требования исторически; «цель будущего scheduled подтверждена» не утверждать. |
| `docs/prompt-persist-production-screening-2026-10-11.md` | ?? | Требование стабильных production flags | **Закоммитить после оформления** | Выполнено `30e3eb4`/PR #14, аналог результата `docs/semantic-admission-production-activation-2026-10-10.md` и README/workflows/Compose. Старые fallback true и запрос создать PR уже не текущее состояние. |
| `docs/prompt-reenrich-and-fix-publication-dates-2026-10-11.md` | ?? | Подробные требования и промежуточные уточнения re-enrichment | **Закоммитить после оформления** | В Git есть реализация `4e46089`, `docs/article-reenrichment.md` и серия pilot/production reports; нет точного аналога истории требований. Заголовок «пилот не оплачен/production не менялся» устарел. Архивная пометка обязательна. |
| `docs/prompt-resume-2026-10-11.md` | ?? | Handoff после PR #14 перед cleanup | **Закоммитить после оформления** | Историческая точка v0.1.78, следующая cleanup уже выполнена PR #15. Связан с старым context и cleanup prompt; сохранить вместе как provenance, не актуальное задание. |
| `docs/prompt-resume-reenrich-2026-10-11.md` | ?? | Handoff с completed prepend и прежним pilot-состоянием | **Закоммитить после оформления** | Начало правильно сообщает массовый apply; нижняя часть снова говорит «mass budget не согласован/production не менялся». Сохранить как исторический документ с явным precedence, указать tracked production report и регулярный release. |
| `docs/prompt-retention-800-days-2026-10-11.md` | ?? | Требование retention 800 с сохранением overrides | **Закоммитить после оформления** | Выполнено `c787ce0`; конкретные аналоги — `tests/unit/test_retention_policy.py`, CLI/scripts/README и cleanup-report. Исторический prompt хранит rationale, не незавершённую настройку. |
| `docs/prompt-verify-daily-cycle-and-resolve-holds-2026-10-11.md` | ?? | Предыдущее задание scheduled/hold диагностики | **Закоммитить после оформления** | Указанные head `6d6ea78`, v0.1.83, scope 50/43 заменены новым report 12 октября и PR #20/#21. Исторические инструкции сохранить; следующая незавершённая проверка вынесена в prompt ниже. |
| `docs/prompt-verify-next-scheduled-daily-cycle-2026-10-12.md` | ?? | Действующий handoff проверки 13 октября | **Оставить до завершения** | Реальная успешная автоматическая публикация ещё не подтверждена. На момент аудита 12 октября 06:36 UTC цикл 13 октября 01:00/02:00 UTC впереди. Сохранить на текущем пути: на него ссылается новый daily-report. Не запускать это задание в рамках очистки. После выполнения включить в отдельный коммит с outcome. |
| `docs/reenrich-stage-checkpoints-2026-10-11.md` | ?? | История последовательности и approval checkpoints | **Закоммитить после оформления** | Содержит уникальную сводку этапов и пользовательской последовательности; аналоги результатов — tracked fetch/pilot/rubric/production reports из `4e46089`. Верхний current status и Outstanding decisions отстают от completed mass/apply. Оформить как журнал этапов, не нынешний блокер. |
| `docs/semantic-admission-agent-prompt-2026-10-10.md` | ?? | Исходное задание semantic gate | **Закоммитить после оформления** | Контракт доставлен `c4bf875` и `dece005`/PR #13; аналог конечного контракта `docs/semantic-admission-spec-2026-10-10.md`. Старое scoring-only и запрет менять production относятся к прежнему этапу. |
| `scripts/weekly_historical_preview.py` | ?? | Самостоятельный runner исторического preview | **Оставить до завершения** | Использовался в оплачиваемом pilot, отсутствует в Git всех локальных refs; имеет отдельные manifest/cache/budget/jobs. Это полезная работа, но support/readiness не закончены: см. отдельный разбор ниже. Не удалять и не коммитить как готовый инструмент автоматически. |
| `session-context-2026-10-10.json` | ?? | Handoff после PR #14 | **Закоммитить после оформления** | Последние verified v0.1.77 и next cleanup/date bug устарели, но сохраняет preferences, scope и pause point. Исторический context, аналог outcome — admission activation, cleanup и article-reenrichment docs. Нет обнаруженных настоящих credentials; есть адрес/пути ops. |
| `session-context-reenrich-2026-10-11.json` | ?? | Многократно дополнявшийся context пилота и mass apply | **Закоммитить после оформления** | Содержит полезные hashes/paths/preferences, но противоречивые approvals и флаги uncommitted. `4e46089`/PR #16 уже доставил код, а завершённый apply отражён в tracked production-report. Только архив с явной пометкой «не использовать для resume»; не утверждать, что достаточно актуализировать один current_stage. |
| `sources.existing.json` | ?? | Exclusion export старого локального registry | **Удалить после правки связанного промпта** | Все 99 IDs и все общие поля точно совпадают с `5e67a05^:sources.yaml`; новых источников нет. Дополнительные language=en/respect_robots=true — defaults, registered_in одинаков у всех 99, hostname/normalized_url вычисляемые. После registry repair 10 записей отличаются от master. Это заменяемая устаревшая выгрузка; её дата/scope зафиксированы ниже. Перед удалением изменить search prompt, чтобы он не требовал отсутствующее вложение. |
| `sources.search-prompt.md` | ?? | Полезный повторно используемый prompt source research | **Закоммитить после правки** | Точные требования JSON/дедупликации/verification/disabled sources не имеют tracked аналога. Ссылка на удаляемый export требует замены на актуальный `sources.yaml` или явно свежую локальную выгрузку. Если YAML: описать defaults и отсутствие production verification. Перенести в `docs/prompt-search-new-sources-2026-10-10.md`, в соответствии с правилом пользователя. Новый поиск/импорт не запускать. |
| `specs/010-weekly-ai-analytics-for-management-dashboard/historical-backfill-diagnostic.md` | ?? | Read-only диагностика и первый outcome preview | **Закоммитить после оформления** | Unique volumes, coverage/provenance limits и usage; tracked `trend-spec.md`/`trend-validation.md` описывают метод, не этот pilot. Состояние до поздней публикации; связанный weekly session-report описывает последующую загрузку. Сохранить исторически, не как текущую production-инструкцию. |
| `tests/unit/test_weekly_historical_preview.py` | ?? | Четыре mock-регрессии runner | **Оставить до завершения** | Импортирует untracked script по точному пути. Подготовка/resume/budget/cache покрыты частично; см. разбор. Удаление/архив одного файла отдельно ломает пару. |
| `weekly-pilot-session-report-2026-10-10.md` | ?? | Поздний outcome pilot, публикация и corrections пользователя | **Закоммитить после оформления** | Не копия diagnostic: включает загрузку snapshot, русскую публикацию, отменённую UI-разработку и ограничения. Это завершённый отчёт с незавершёнными follow-up, не приказ их выполнять. Unique evidence сохраняется; статус weekly=true и «на сайте сейчас» только на дату сессии. |
| `docs/uncommitted-files-audit-2026-10-12.md` | новый отчёт | Аудит, evidence и конкретный план | **Закоммитить** | Создан в разрешённом scope. Не содержит corpus/provider responses/credentials. Фиксирует уточнённую классификацию, зависимости и основания, чтобы очистка была reviewable. |

## Weekly-preview: самостоятельная работа, которую нельзя потерять

Пара script/test не закоммичена ни на master, ни в локальной исторической feature-ветке: `git log --all -- <оба пути>` пуст. Имя ветки не означает сохранения файлов в Git.

По коду:
1. `prepare` фиксирует 1–5 packet, consecutive Sunday dates, complete input, общую taxonomy/configuration, исходные legacy reports и input fingerprint.
2. `PreviewStore` сохраняет SQLite decisions/progress/jobs и cumulative HTTP-attempt budget. Unknown usage сохраняет полную reservation; retries учитываются.
3. `run` переиспользует классификацию/cluster и записывает отдельные JSON revision. Production writer/WeeklyStore.publish не вызывается.
4. Output — historical_preview, coverage_confirmed=false; new/up/down пустые. Классификация исторических данных не доказывает coverage.
5. Shared app dependencies актуально присутствуют: `WeeklyEnricher`, `windows`, `explain`, `encoded`, `fingerprint`. Это не dead code из-за пропавшего импорта.
6. Four mock tests проверяют неизменность manifest, отсутствие оплаты prepare, долговечность бюджета, pre-request retries и reuse после resume. AST обоих файлов разбирается без выполнения.

Исторические документы подтверждают реальный pilot 1128 inputs, 3844 JEV и 340 DeepSeek attempts, recorded $0.316503. Это уже полученный полезный результат; новые расчёты ради аудита запрещены.

Но **готовность к поддерживаемому инструменту не подтверждена**:
- Full repo gates и live semantic evaluation для этой пары не зафиксированы; результаты прежних scoped tests из документов не являются текущим прогоном.
- Hardcoded PRICES/off-peak/cache-hit logic — snapshot старой pricing methodology; перед новым paid run требуется отдельная проверка актуальности. Цены в этом аудите не переутверждались.
- Статически видимый случай: `weekly_narrative.explain()` ловит `BudgetExhausted` и возвращает false; driver может затем отметить job complete с template, не сообщив отдельный narrative budget stop. Нужны ожидаемый контракт и mock-регрессия до коммита инструмента.
- `prepare` создаёт manifest до получения run.lock. Concurrent prepare с разными inputs требует проверки, чтобы frozen manifest не был записан двумя процессами до lock.
- fcntl ограничивает переносимость Unix; путь root содержит private manifest/source text/decision cache, его нужно документировать как private ignored storage.
- Схема output не является готовым publication payload: отдельный operator publisher упомянут только в ignored исторических artifacts. Script сам не публикует.
- Диагностический документ и поздний session-report описывают разные моменты: первоначальное «не публиковалось» нельзя выдавать за итог после загрузки snapshot.

Рекомендация: **сохранить оба файла на месте как незавершённый отдельный scope**. Следующая разрешённая задача по ним — решить, поддерживать ли инструмент, оформить контракт и выполнить только offline mocks/quality gates. Ни этот аудит, ни очистка не разрешают запускать weekly, платить модели, редактировать historical publications или доделывать UI.

## Устаревшие утверждения и чувствительность

1. `session-context-2026-10-10.json`: production v0.1.77, PR14 pending deployment, cleanup следующая, fallback discovery-date ещё не исправлен. Эти утверждения исторические и заменены PR #15–#21.
2. Большой re-enrich context одновременно содержит completed_mass_stage/current_stage и mass budget still unapproved, production zero changes, source_changes_committed=false, pinned local image, old head. Верхний created_at относится к прежнему состоянию. Не использовать файл как источник текущих разрешений/ветки/остатка бюджета.
3. `reenrich-stage-checkpoints` остановлен на candidate-v3/$0.196297 и ожидании mass budget; фактический completed outcome уже в `docs/reenrich-production-results-2026-10-11.md`.
4. В re-enrich/resume prompts и старом daily-cycle prompt остались несовместимые current-state фразы. Сохранить историю; добавить короткий архивный заголовок/индекс с датой и ссылкой на конечный outcome. Не переписывать прежние receipts задним числом.
5. Новый daily-report 12 октября осторожно различает scheduled failure и manual resume. Его 854 tests/coverage — авторский receipt предыдущей работы, не результат этого аудита. Следующий scheduled цикл остаётся незавершённым.
6. Даже tracked `docs/reenrich-production-results-2026-10-11.md` содержит исторический pinned local image и «uncommitted»; уже tracked daily-report объясняет переход к v0.1.80 и последующим registry releases. Этот аудит не правит tracked исторические отчёты.
7. Weekly diagnostic сообщает конец на v0.1.75/weekly=true; поздний report сообщает русскую публикацию. PR #14 и последующие документы закрепили weekly-off. Язык исторического snapshot на сегодняшний production не перепроверялся.

В исследованных 24 файлах **не обнаружены настоящие API tokens, пароли, private keys или URL с embedded credentials**. Проверены характерные форматы и assignments, поля JSON и текстовая структура; это ограниченная проверка этих файлов, не сертификация всех секретов репозитория.

Большой context содержит явно обозначенный public local-test auth placeholder в командных примерах: это не обнаруженная production credential. При архивном коммите сохранить явную маркировку либо заменить пример на `<LOCAL_TEST_SECRET>`. Контексты/отчёты содержат machine usernames, абсолютные local/server paths, SSH host, operational hashes и финансовые агрегаты; не путать их с credentials. Перед публикацией архивов вычитать embedded commands и идентифицирующие local paths, при необходимости сделать их относительными с сохранением смысла. Не переносить реальные secrets из .env.

Raw corpus/provider responses из tmp/ не читались и не копировались. Большие JSON contexts прочитаны как контекст/метаданные с ограниченным выводом; source export разобран целиком программно. Private corpus не нужен для решения, коммитить ли эти файлы.

## Source export: точный аналог и условие удаления

`sources.existing.json`:
- exported_at: 2026-10-10T10:56:01.308223+00:00;
- scope: local sources.yaml и read-only local SQLite; production_registry_verified=false;
- 99 sources, 88 enabled, 11 disabled, 42 html/57 rss;
- local DB source_count=100, один e2e fixture исключён;
- у всех 99 registered_in одинаков: sources.yaml и data/ai_news.db; language=en и respect_robots=true;
- все IDs и общие поля совпадают с историческим `5e67a05^:sources.yaml`, текущие defaults сохранены в sources.yaml.

После `5e67a05` изменены common fields десяти источников:
deepmind_blog, microsoft_ai_blog, rainbird, promptengineering_blog,
vellum_blog, theagi_company_blog, e2b_blog, linguamatics, dify_blog,
outerbounds_blog. Конкретный описание repair уже tracked:
`specs/011-json-source-intake/registry-repair.md` и `scripts/repair_source_registry.py`.

Следовательно, это не потеря единственного списка источников: старые common values доступны из Git, актуальные — из master. Вычисляемые normalized_url/hostname воспроизводимы, snapshot provenance сохранён в этом отчёте. Файл нельзя продолжать прикладывать как актуальный exclusion registry.

Удаление согласовывать и выполнять **вместе** с правкой search prompt: заменить ссылку/формат вложения на текущий sources.yaml с defaults и явным local-only scope либо на действительно свежую private выгрузку. Текущий DB/production registry этим аудитом не сверялся. Не обещать, что YAML отражает все production sources.

## Ignored/private storage: сохранить

Проверены только directory entries относящихся к задаче каталогов и ignore rules. Не выполнены recursive чтение корпуса, du всего диска или анализ private journals.

- `.gitignore:11` — tmp/; `.gitignore:10` — data/; `.gitignore:16` — .env.
- `.gitignore:15` — конкретный локальный multi-agent-orchestration-universal skill.
- global excludesfile содержит только *~ и .DS_Store; active lines в .git/info/exclude отсутствуют.
- git ls-files tmp data .env пуст: protected каталоги не tracked.
- `.codex/rules/` содержит единственный operations.rules; других файлов rules не обнаружено.

| Каталог/группа | Что видно без чтения corpus | Действие |
|---|---|---|
| `tmp/reenrich-2026-10-11/` | 73 immediate entries, 2 dirs/71 files; планы, journal, usage, cache-verification, receipts и pages | Сохранить целиком приватно; paid/recovery artifacts, не мусор |
| `tmp/legacy-jev-cleanup-run/` | 9 entries; journal, snapshot, manifest, restore-verification, unresolved review | Сохранить целиком |
| `tmp/daily-cycle*`, `tmp/scheduled-*`, `tmp/cognition-*`, `tmp/local-input-*` | Operational backups/diagnostics/receipts по именам | Сохранить; не включать в Git и не удалять по glob |
| `tmp/weekly-*` и связанные operator scripts | Historical export/pilot/status/publication review copies | Сохранить оплаченные результаты, не запускать повторно |
| `tmp/source_audits/`, `tmp/source_repair/` | 2 и 45 immediate entries; research/repair evidence | Сохранить; HTML и raw verification не переносить в docs archive |
| `tmp/runs/` | 11 immediate directories/links; handoffs/logs | Сохранить в текущем workflow storage |
| `tmp/worktrees/` | Пустой на момент проверки | Вне очистки: пустота не основание запуска общего удаления |
| `data/` | local DB и каталог antigravity | Сохранить, содержимое не читалось |
| `.env` | Ignore подтверждён; содержимое не читалось | Сохранить без вывода secrets |

**Новые .gitignore rules сейчас не нужны.** Shared archive предложен tracked в docs; незавершённый код остаётся видимым в git status. Не добавлять docs/, .codex/, scripts/, tests/, session-context-*.json или prompt-*.md в ignore ради косметического чистого дерева.

## Конкретные группы коммитов и порядок

Все группы предлагаются для последующей отдельно согласованной реализации. Запрещено автоматически добавлять весь docs/ или .codex/.

1. **Правило handoff** — только AGENTS.md, без правок требований.
   Предлагаемый title: `docs: preserve prompts for session handoffs`.

2. **Daily outcome 12 октября** — только docs/daily-cycle-verification-results-2026-10-12.md.
   Title: `docs: record scheduled daily failure and v0.1.85 recovery`.
   Ссылка на ещё локальный next-session prompt обозначает рабочий handoff: его отсутствие в чистом checkout не должно выглядеть как отсутствующая committed инструкция. До коммита либо пометить этот путь как local pending task, либо включить prompt в отдельный outcome-коммит после завершения проверки. Не выдумывать successful scheduled result.

3. **Завершённая история admission/cleanup** — 6 файлов:
   pr-13-review, semantic-admission-agent-prompt, prompt-persist-production-screening,
   prompt-cleanup-legacy-articles-jev, prompt-retention-800-days,
   session-context-2026-10-10.json.
   Title: `docs: archive completed admission and cleanup handoffs`.

4. **Завершённая история re-enrichment/daily** — 7 файлов:
   prompt-reenrich-and-fix-publication-dates, prompt-resume, prompt-resume-reenrich,
   prompt-fix-daily-publication, prompt-verify-daily-cycle-and-resolve-holds,
   reenrich-stage-checkpoints, session-context-reenrich-2026-10-11.json.
   Title: `docs: archive completed re-enrichment and daily handoffs`.

5. **История weekly pilot** — diagnostic и weekly-pilot-session-report, 2 файла.
   Title: `docs: preserve historical weekly pilot outcome`.
   Сохранить поздний outcome и прежнюю диагностику как разные точки времени. Не включать незавершённый runner/test в этот docs-коммит и не запускать weekly.

6. **Повторно используемый source research prompt** — исправленный sources.search-prompt.md под именем docs/prompt-search-new-sources-2026-10-10.md, 1 файл.
   Title: `docs: use current source registry in research prompt`.
   Проверить, что ссылка на sources.existing.json удалена и формат нового вложения описан корректно. Только после этого удалить export.

7. **Задание аудита и отчёт** — docs/prompt-audit-uncommitted-files-2026-10-12.md и этот report, 2 файла.
   Title: `docs: record uncommitted files audit and agreed cleanup plan`.
   Не описывать план как уже выполненный. Если план будет изменён при согласовании, обновить outcome в отчёте отдельно.

Для групп 3–5 понятное место — **tracked** `docs/archive/2026-10-10-12/`.
Сохранять внутри исходную структуру относительно корня репозитория:
`docs/...`, `session-context-...json`, `specs/010-.../...` и root weekly report.
Тогда связи между архивными docs/context/specs не теряются. Создать небольшой archive README с completed/superseded statuses, precedence поздних результатов и ссылками на современные tracked outcomes; относительные ссылки на современные docs при переносе пересчитать. Ссылки на private tmp paths оставить как исторические recovery pointers, не публикуя содержимое.
Archive README будет новым служебным файлом реализации, не входит в текущие 25 кандидатов.

Не смешивать historical facts и действующие инструкции. Архивный контекст должен прямо запрещать использование устаревших head/approvals/commands как resume. Полезное правило пользователя про сохранение всех последующих prompts остаётся в AGENTS.md и будущих handoffs.

## Точный список кандидатов на удаление

1. `.codex/rules/operations.rules` — локальные permissions и отсутствующий machine-specific helper; после согласования принять потерю этих file-based shortcuts. Это не очистка всех Codex settings.
2. `sources.existing.json` — после согласования и связанной правки источника вложения в search prompt; исторические общие данные уже в `5e67a05^:sources.yaml`, provenance зафиксирован здесь.

Других кандидатов нет. В частности, weekly script/test, действующий scheduled prompt, private caches/journals/backups/receipts не кандидаты на удаление. Исторические prompts с уникальными требованиями не объявлены мусором только из-за даты или untracked status.

## Проверки этого аудита и будущей реализации

Выполнены: Git inventory/diff/tree/history/ancestry; live remote head/tag; GitHub PR list; чтение каждого кандидата в необходимом объёме; exact blob comparison с origin/master; поиск ссылок; source JSON/schema/metadata/history comparison; limited credential scan; shallow directory/ignore review; AST parse двух Python файлов без импорта/выполнения; ps/lsof и сравнение SHA/mtime.

**Ни один исходный кандидат не является точным blob-дубликатом файла в origin/master.**
Сходство завершённой задачи и опубликованного outcome не названо побайтовым дублем. Для source export показана более точная проверка исторических общих полей с конкретной Git revision.

Полный lint/pytest не запускались: аудит не меняет runtime и это прямо предусмотрено заданием. Scoped weekly mocks также не запускались: AST/static review достаточны для классификации, текущая работоспособность runner не заявляется. Не проверялись production/API/provider pricing/состояние corpus или оплаченные journal contents.

Перед будущими commit/push прочитать dev-quality-gate и выполнить обязательные:
`make lint PYTHON=./venv1/bin/python` и `./venv1/bin/pytest`, с нужной изоляцией SQLite/PostgreSQL. Для manual edits применять apply_patch. Перед любым переносом/удалением сверить inventory hashes и ссылки, затем staging строго по списку; приватное tmp/ не включать даже при готовых gates.

## Контрольные суммы исходного снимка

SHA-256 приведены полностью для повторной проверки и предотвращения перезаписи работы другой сессии. Отчёт исключён из исходного snapshot, поскольку создаётся этим аудитом.

| Путь | SHA-256 |
|---|---|
| `AGENTS.md` | `027066a24eb151a7325b15b033aef48c88df5057ccaa26ea8e8d65f47fc4c08e` |
| `.codex/rules/operations.rules` | `9d3b0e66b3d18ac459d465be991cadc25ea7bec0afc9f65d3337326ba9245de9` |
| `docs/daily-cycle-verification-results-2026-10-12.md` | `156182c3d11e14e1bf7bc32cbab350b102d002ec0a00a11cca3e8c33c951db01` |
| `docs/pr-13-review-2026-10-10.md` | `073fbe116097ee4168d97be1cda2ac1f4a378bc65426ae4c97b7e2b94be95e1e` |
| `docs/prompt-audit-uncommitted-files-2026-10-12.md` | `f4794eae9c4cc5914228a5e0cc00110aee84f565feac181c34690d87b62ac97a` |
| `docs/prompt-cleanup-legacy-articles-jev-2026-10-11.md` | `c09ac0e3bbd6f0b7461ab4afe2d4338a94a97867235095636d250499541f6a33` |
| `docs/prompt-fix-daily-publication-2026-10-11.md` | `1e29e3184d5378eaec72d1465504b9e1065961d74eaffc889cb39a191d6cb1e2` |
| `docs/prompt-persist-production-screening-2026-10-11.md` | `ee4299f98bd801b718f00d8ce00b21e7bc0e1a471b0d17cc165f0a75113adc39` |
| `docs/prompt-reenrich-and-fix-publication-dates-2026-10-11.md` | `fddd6948afdf929ba028accbd604e30c1625b49435c2cc4ad9df9011802db409` |
| `docs/prompt-resume-2026-10-11.md` | `b305a7404e8fa1f4568401e70e4ed5d5bb3113cb9c98083b55dbb1d221618621` |
| `docs/prompt-resume-reenrich-2026-10-11.md` | `240013efa399b9290a90436861ace580c5b806b80aaa158bf4bb00134afb5384` |
| `docs/prompt-retention-800-days-2026-10-11.md` | `70f53224f23059d30975c669b0febfbb12be685943816624ec40023194e15809` |
| `docs/prompt-verify-daily-cycle-and-resolve-holds-2026-10-11.md` | `fa591132d53b7ae21eb7b96465c317ded945edef9a2bbd71f4f15f19e016a79e` |
| `docs/prompt-verify-next-scheduled-daily-cycle-2026-10-12.md` | `b76ccabc921472a48b424f929830b507570bf83ebd3e44ef326108afec90d094` |
| `docs/reenrich-stage-checkpoints-2026-10-11.md` | `c8537b271d4d460d6c42a3ad26572311cb6a96998f1a96f0339624fae9d5d19e` |
| `docs/semantic-admission-agent-prompt-2026-10-10.md` | `eb95d36e333810af984f957366f921e4d0e2229194153456c2d422355b73a1e5` |
| `scripts/weekly_historical_preview.py` | `9224f46f513255da86ed74d06a9e004e149b9356f740343a8170a682c06552b1` |
| `session-context-2026-10-10.json` | `1e9803492469869fa4a2013eb65a9af7960bbef7f29dec7fd153dcfb511dae77` |
| `session-context-reenrich-2026-10-11.json` | `91659d559fdfc9fa06e80ad45f174e40bd599ebefb4ee3210de2f762b84b7cb6` |
| `sources.existing.json` | `ff98b6d1dcc72973d4364147f051f4af40fc785a83cc07b8e0d3b5569d37247f` |
| `sources.search-prompt.md` | `90e3a0bc654a7ee6332758b510b64c0ba65f08a617636d6dde7c70e14d0de087` |
| `specs/010-weekly-ai-analytics-for-management-dashboard/historical-backfill-diagnostic.md` | `0e7f5476e7a1e5029f6cc58a8d24d8edde807b9351bc913375a9c2a280f324b4` |
| `tests/unit/test_weekly_historical_preview.py` | `037949c00f4d3b0a1f7a335e68d5f73ffc3ecd63bac30420ab012f90be3f3a63` |
| `weekly-pilot-session-report-2026-10-10.md` | `21c1c2a28292f9ba1173e84b9d7ae5588c7620d009d8219f0a9bc56778fceb86` |
