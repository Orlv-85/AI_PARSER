# PR #39: verification of the fix diff — GPT-6, 2026-10-19

**Вердикт: merge after fixes.** Четыре новых дефекта V01–V04 и неполное исправление F10
(V05). Репозиторные проверки проходят, но не покрывают описанные ниже переходы состояния.

- Проверенный SHA: **`1d7904c37e4974b6770859e29ae8fe9bd7e0a1a6`**; повторно сверён с PR перед
  завершением. База исправлений: `8f30549a07225b17d1f8a7187b1d4956b174ecb6`.
- PR: https://github.com/Orlv-85/AI_PARSER/pull/39.
- Detached worktree: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-verify-gpt6`, сохранён.
  `.env` отсутствует; tracked/untracked status перед записью отчёта чистый.
- Область: только исправления F1–F22, N1–N3 и их взаимодействия. Прочитаны consolidated review,
  fix prompt, окончательное решение F19, четыре исходных review, описание PR, spec/plan и
  `dry-run.md`, включая разделы 8–10. Полного повторного review feature не проводилось.
- Код и тесты PR не изменялись. В основной рабочей папке добавлен только этот отчёт.
  Нет provider calls, production access, commit, push или комментариев в PR.

## Команды и результаты

Рабочий каталог команд проверки — detached worktree, кроме явно указанных baseline-копий.
Python — `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python`, `PYTHONPATH=src`.

| Проверка | Результат |
| --- | --- |
| `rtk git fetch origin`; `rtk proxy gh pr view 39 --json headRefOid,body,title`; `rtk git worktree add --detach ../AI_PARSER-verify-gpt6 1d7904c37e4974b6770859e29ae8fe9bd7e0a1a6`; diff от `8f30549` | Выполнены; 39 изменённых файлов |
| `rtk proxy make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python` | **PASS**: ruff; mypy — 173 файла; pylint — 10.00/10. Первый запуск был заблокирован sandbox при создании `.ruff_cache`; разрешённый повтор прошёл |
| Полный pytest, **один запуск**, с отдельным PostgreSQL 18 | **1172 passed, 0 skipped**, exit 0. Дополнительный collect-only подтвердил 1172 теста; повторного полного запуска не было |
| `rtk proxy sh -c 'for f in scripts/*.sh; do bash -n "$f" || exit; done'` | **PASS**, проверен каждый script, exit 0 |
| SQLite migrations, включая parity, previous-head upgrade, create_all и downgrade | **PASS**, существующие `test_daily_signals_migration.py` в полном suite |
| Независимый PostgreSQL migration probe, `/private/tmp/test_pr39_pg_fix_verify_gpt6.py` | **1 passed**: previous head → head → downgrade → create_all → head → повторный upgrade → downgrade → head; обе новые hash-колонки NOT NULL; schema parity; сохранение статьи и digest-таблиц |
| Новые тесты поверх исходников `8f30549`, без изменений PR worktree | **26 failed, 2 passed**; реальные assertions/ошибка render, а не collection failures. Лог: `/private/tmp/pr39-baseline-gpt6.log` |
| Дополнительные extract/compute тесты на `8f30549` с минимальным collection bridge | **5 failed, 2 passed**: F7/F8/F19/F22 падают на проверке поведения; F18 unit test — на старой сигнатуре. Два PASS — независимые probes V03/V04, подтверждающие отсутствие этих регрессий в базе |
| Два теста окончательного решения F19 поверх `216d9f1` | **2 failed** на assertions; на проверяемом head оба проходят |
| Независимые проверки желаемого поведения, `/private/tmp/test_pr39_fix_verify_gpt6.py` | **7 failed** на assertions, подтверждают V01–V05. Это дополнительные review probes вне suite PR; лог `/private/tmp/pr39-fix-gpt6-probes.log` |
| F18 input/grounding/hash probes, `/private/tmp/test_pr39_input_fix_verify_gpt6.py` | **2 passed** |
| `rtk proxy node /private/tmp/pr39_fix_verify_gpt6_js.cjs` | **PASS**: настоящий date-change handler из head HTML, loading, независимый запрос signals при отказе digest, 503/error text, unavailable и игнорирование позднего ответа другой даты |

Полный suite запускался так:

```sh
rtk proxy /Users/vyacheslavorlovskiy/.codex/bin/run-pytest \
  --python /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python \
  --env PYTHONPATH=src \
  --env AINEWS_TEST_POSTGRES_URL=postgresql+psycopg://ainews_test:isolated_ci_test@127.0.0.1:55441/ainews_test \
  -- -q
```

Для PostgreSQL создан собственный контейнер:

```sh
rtk docker run -d --rm --name ainews-verify-gpt6-pg \
  -e POSTGRES_USER=ainews_test -e POSTGRES_PASSWORD=isolated_ci_test \
  -e POSTGRES_DB=ainews_test -p 127.0.0.1:55441:5432 postgres:18-alpine
```

Это исключительно тестовые credentials. Существующие локальные БД не использовались.
После проверок контейнер остановлен через `rtk docker stop ainews-verify-gpt6-pg` и удалён
его `--rm` lifecycle.

Baseline подготовлен через `git archive 8f30549` в `/private/tmp/pr39-verify-gpt6-base`;
туда скопированы новые test files. Скрипты подготовки/запуска:
`/private/tmp/prepare_pr39_baseline_gpt6.py`, `/private/tmp/run_pr39_baseline_gpt6.py`.
Для двух модулей baseline не имеет импортов `input_kind`/`LexicalHistory` и параметра `history`:
`/private/tmp/pr39_baseline_shim_gpt6.py` предоставляет только заглушки для collection и удаляет
новый параметр при создании старого SnapshotInput; исправленная логика в baseline не переносилась.
F18 дополнительно падает на содержимом запроса в интеграционном run test без этого bridge.

Исключения из утверждения PR «каждый тест падает на 8f30549»: кроме известного
`max_calls=0`, проходит `test_lexical_history_reads_digest_text_not_article_summaries` — в базе
ещё вообще нет lexical suppression. Это осмысленный negative test для промежуточной реализации:
он и `test_lexical_hit_in_not_yet_released_text_is_ignored` проверены отдельно на `216d9f1`,
где оба падают. Эта особенность сама по себе не дефект продукта.

## Проверка каждого finding

Все пути и номера строк ниже относятся к проверенному SHA. Имена test files в таблице находятся
в `tests/unit/`. **H** = проходит на head в полном suite; **B** = падает на `8f30549` в
описанном baseline-прогоне; **B\*** = тот же результат с collection bridge.
`yes` оценивает исходный finding; новые взаимодействия отдельно перечислены в V01–V05.

| ID | Fixed | Evidence: code; test; result | Примечание |
| --- | --- | --- | --- |
| F1 | yes | `src/app/core/daily_signals.py:218`; `test_daily_signals_run.py::test_backfill_recomputes_through_latest_completed_day` — H/B | Верхняя граница recompute — max(report date, вчера UTC), включая recompute-only |
| F2 | yes | `src/app/core/daily_signals_entities.py:306`, `:397`; `test_daily_signals_overrides.py::test_merge_of_vendor_class_entity_moves_its_vendorless_mentions`, `::test_alias_keeps_first_seen_of_the_whole_entity` — H/B | Override применяется после автоматической группировки, захватывает vendorless members и сохраняет first_seen. Отдельная регрессия при plural growth — V04 |
| F3 | yes | `src/app/core/daily_signals.py:249`; `src/app/core/daily_signals_entities.py:306`, `:466`; `test_daily_signals_overrides.py::test_merge_of_needs_review_entity_takes_only_vendorless_mentions`, `::test_overlapping_selectors_refused` — H/B | `?` отделён от пустого селектора; исходный случай OpenAI/Google Atlas не смешивается; overlap refusal проверен |
| F4 | yes | `src/app/core/daily_signals_entities.py:241`, `:258`, `:328`; `test_daily_signals_overrides.py::test_merge_survives_vendor_class_growth` — H/B | Сохранённый vendor selector разрешается через текущий класс Google DeepMind → Google |
| F5 | yes | `src/app/web/signals_view.py:75`; `src/app/web/app.py:501`; `test_web_public_digest.py::test_trend_without_expected_value_and_any_render_error_keep_page` — H/B | None форматируется безопасно; RuntimeError из signals не обрушает digest |
| F6 | yes | `docs/daily-signals.md:165`; `specs/006-daily-ai-signals/plan.md:1003`; описание PR | Порядок downgrade feature image → старый release согласован; вариант keep-schema сохраняет migration file. Это документационное исправление, отдельного regression test нет |
| F7 | yes | `src/app/core/daily_signals_extract.py:184`; `test_daily_signals_extract.py::test_grounding_normalizes_typographic_quotes_and_dashes` — H/B* | NFKC и переводы кавычек/тире симметричны |
| F8 | yes | `src/app/core/daily_signals_extract.py:270`; `test_daily_signals_extract.py::test_stoplisted_entities_do_not_use_primary_or_entity_slots` — H/B* | Stoplist до обоих caps; тест проверяет primary slots и восьмую реальную entity |
| F9 | yes | `src/app/storage/daily_signals.py:64`, `:168`, `:407`, `:437`; migration `b6d1f0a7c3e5_add_daily_signals.py:35`, `:56`; `test_daily_signals_repo.py::test_reused_article_id_without_fk_enforcement_inherits_nothing` — H/B | Scope, cache, coverage, observations и записи evidence проверяют id+hash; глобальный SQLite pragma не менялся. SQLite/PG migrations и create_all parity прошли |
| F10 | partially | `src/app/storage/daily_signals.py:281`; `test_daily_signals_repo.py::test_newer_ok_extraction_without_entities_supersedes_old_mentions` — H/B | Исправлено при живой ArticleSignal; после cascade retention старые mentions возвращаются — V05 |
| F11 | yes | `src/app/core/daily_signals.py:100`, `:150`; `test_daily_signals_run.py::test_incomplete_retry_attempt_keeps_the_retry`, `::test_changed_content_of_skipped_article_is_not_a_retry` — H/B | Незавершённый retry не расходует retry_used, следующий `--retry-skipped` использует те же retry bodies; изменённый hash идёт обычным запросом |
| F12 | yes | `src/app/core/daily_signals.py:135`, `:144`; `test_daily_signals_run.py::test_article_on_several_backfill_days_is_attempted_once` — H/B | Invocation-level attempted set предотвращает повторный dispatch общей статьи на разных днях |
| F13 | yes | `src/app/core/daily_signals_entities.py:292`, `:435`; `test_daily_signals_entities.py::test_base_token_tie_does_not_depend_on_insertion_order` — H/B | Tie-break использует также token tuple; перестановка insertion IDs проверяется |
| F14 | yes | `docs/daily-signals.md:76`; `docs/configuration.md:102`; описание PR | Явно указано, что production passthrough есть только для ENABLED; caps через CLI. Docs-only, тест не заявляется |
| F15 | yes | `docs/daily-signals.md:157`; `specs/006-daily-ai-signals/plan.md:660`; описание PR | Recovery требует целого deploy с тем же target, а не только Alembic. Docs-only; реальный deploy не выполнялся |
| F16 | yes | `src/app/web/digest.html:492`, `:647`; `test_web_public_digest.py::test_signals_reload_on_date_change_independent_of_digest` — H/B; Node probe — PASS | Статическая проверка дополнена исполнением фактического handler с управляемыми fetch |
| F17 | yes | `scripts/run_daily_digest_job.sh:34`, `:42`, `:46`; `test_deepseek_digest.py::test_daily_job_without_timeout_binary_skips_signals`, `::test_daily_job_signals_failure_keeps_success_and_removes_container` — H/B | Без timeout signals пропускается; cleanup ограничен `timeout -k 10 60`; publish определяет exit status |
| F18 | yes | `src/app/core/daily_signals_extract.py:140`, `:147`, `:154`; `src/app/core/daily_signals.py:87`, `:114`; `test_daily_signals_extract.py::test_short_content_falls_back_to_title_and_summary`, `test_daily_signals_run.py::test_history_article_without_body_uses_summary_and_records_input_kind` — H; run test B | Один текст для request/hash/grounding; HTML cleanup, cap, provenance input. Дополнительные probes JSON envelope и hash — PASS |
| F19 | partially | `src/app/storage/daily_signals.py:477`; `src/app/core/daily_signals_compute.py:267`; `test_daily_signals_compute.py::test_new_suppressed_by_title_or_summary_history` — H/B*; `test_daily_signals_repo.py::test_title_only_history_suppresses_new_through_digest_text` — H/B; оба decision tests — H/fail на 216d9f1 | Digest-only source, cache и payload records есть, но prerelease в скобках теряется и single-token vendor guard слишком слаб — V01/V02 |
| F20 | partially | `src/app/core/daily_signals_entities.py:79`, `:213`; `test_daily_signals_entities.py::test_glued_company_suffix_joins_vendor_class`, `::test_glued_suffix_needs_a_matching_member` — H/B | LiquidAI/Liquid AI исправлено; OpenAI ошибочно объединяется с отдельным Open — V03 |
| F21 | partially | `src/app/core/daily_signals_entities.py:339`; `test_daily_signals_entities.py::test_trailing_plural_joins_singular_only_when_singular_exists` — H/B | Базовый plural fold и исключения Atlas/Genesis/Nexus работают; существующий merge не переживает появление singular — V04 |
| F22 | yes | `src/app/core/daily_signals_compute.py:230`, `:386`; `test_daily_signals_compute.py::test_generic_lowercase_feature_names_are_not_new` — H/B* | Отсечение только из New; причина сохраняется в new_suppressed; observations для stories/trends не удаляются |
| N1 | yes | `src/app/web/app.py:180`; `test_web_public_digest.py::test_placeholders_in_digest_text_are_not_substituted` — H/B | Single-pass substitution не обрабатывает повторно вставленный текст |
| N2 | yes | `scripts/run_daily_digest_job.sh:17`; `test_deepseek_digest.py::test_daily_job_ignores_inherited_lock_marker` — H/B | Handshake — аргументы `--locked DATE START`; inherited marker не отменяет flock |
| N3 | yes | `src/app/config/settings.py:77`; plan `:215`, `:514`; `test_settings.py::test_daily_signals_cap_bounds` — H, три новых границы B | Прежняя граница calls=0 уже работала; 401-дневный inclusive window и March/May отражены в плане |

## Новые дефекты исправлений

### V01 — major — F19 удаляет prerelease qualifier до проверки

**Место:** `src/app/core/daily_signals_compute.py:270`, `:296`; вызываемый
`src/app/core/daily_signals_entities.py:55` (`clean`). **Confidence: confirmed.**

LexicalHistory применяет к целому digest text нормализацию имени `clean()`, которая удаляет
содержимое скобок. Текст `Acme announces Atlas Pro (preview).` превращается в
`Acme announces Atlas Pro .`; NOT_RELEASED больше не видит `preview`. При GA на D Atlas Pro
неправильно исчезает из New. Аналогично `(early access; will launch next month)`.

Оба параметра `test_parenthetical_prerelease_does_not_suppress_ga` падают: expected
`['Atlas Pro']`, actual `[]`. Payload сохраняет уже обрезанный текст без qualifier, поэтому
оператору также не видно причины ложного подавления. Это нарушает окончательное решение F19
о GA после preview.

**Предлагаемое исправление:** хранить полный digest text; проверять NOT_RELEASED и строить snippet
по тексту без удаления скобок. Для lexical matching использовать отдельную нормализацию.
Добавить parenthetical preview/beta/early-access regression cases.

### V02 — major — F19 не обеспечивает vendor co-occurrence для single-token имён

**Место:** `src/app/core/daily_signals_compute.py:287`, `:304`. **Confidence: confirmed.**

Условие `(not vendor or bool(vendor & set(toks)))` допускает подавление без vendor вообще,
а для составного vendor достаточно любого его слова. Поэтому:

- новая модель `Beam` с vendor=None подавляется историческим `Beam search improves decoding.`;
- новая модель `Beam` от `Acme Labs` подавляется `Beam search is used in research labs.`,
  хотя Acme там не упомянут: совпадает только общий токен `labs`.

`test_single_token_without_vendor_does_not_suppress_homonym` и
`test_generic_vendor_word_is_not_vendor_cooccurrence` падают: expected `['Beam']`, actual `[]`;
в обоих случаях записан `reason=lexical_history`. Fix prompt требует exact-case single token
**с vendor co-occurrence**. Исходный тест проверяет отсутствующий однословный Reflection,
но не эти два случая.

**Предлагаемое исправление:** для single-token имени без цифр требовать идентифицируемый vendor
и совпадение его нормализованного имени/явного alias, а не любого слова. При неизвестном vendor
не использовать этот слабый lexical hit для подавления New.

### V03 — minor — F20 объединяет OpenAI с отдельным Open

**Место:** `src/app/core/daily_signals_entities.py:79`, `:213`. **Confidence: confirmed.**

`glued_forms('openai')` включает `open`. Если в evidence появляется отдельный org/vendor `Open`,
union-find объединяет классы: `VendorClasses(['OpenAI', 'Open'], [('openai',), ('open',)])`
возвращает `open` для обоих. Это может объединить одноимённые продукты этих разных vendors и
изменить family suppression/overrides. Наличие отдельного короткого имени не доказывает, что
последние буквы длинного являются company suffix.

`test_openai_does_not_join_unrelated_open` **PASS на 8f30549, FAIL на head**. Репозиторный тест
проверяет OpenAI только без конкурирующего Open и поэтому не выполняет полностью требование
F20 «OpenAI must not become open».

**Предлагаемое исправление:** не объединять glued spelling с голым suffix-stripped remainder
только по совпадению формы. Требовать подтверждающее написание с отдельным company suffix
(Liquid AI / LiquidAI), явный alias или другой однозначный признак; добавить negative collision test.

### V04 — major — F21 делает сохранённый merge неработающим при появлении singular

**Место:** `src/app/core/daily_signals_entities.py:349`, `:330`, `:333`.
**Confidence: confirmed.**

Сначала в evidence есть `Gemini Agents` и `Gemini Studio`. Оператор объединяет первую entity
со второй; mentions принадлежат `manual:1`. На следующем дне появляется `Gemini agent`.
`_fold_plurals()` меняет base key всех старых plural mentions на `geminiagent`, но сохранённые
`match_key`/`target_base_key` override не разрешаются через такую же эквивалентность.
После recompute прежние `Gemini Agents` покидают `manual:1` и становятся
`auto:artifact:geminiagent`. Override остаётся в БД без предупреждения.

`test_merge_survives_later_singular_evidence` **PASS на 8f30549, FAIL на head**; проверяется
реальный `merge_entities`, сохранение override и два recompute. Named F21 test содержит обе
формы с самого начала, поэтому такой переход не покрывает.

**Предлагаемое исправление:** разрешать сохранённые source/target base selectors через текущую
plural equivalence так же последовательно, как vendor classes, включая conflict detection.
Проверить позднее появление singular для source и target merge/alias.

## Неполное исправление исходного finding

### V05 — minor — F10 снова проявляется после retention

**Место:** `src/app/storage/daily_signals.py:287`, `:295`. **Confidence: confirmed.**

Для одной идентичности v-old извлекает `Old Name`, v-new успешно извлекает пустой список.
Пока статья существует, `load_evidence()` правильно возвращает `[]`. Удаление статьи с
FK CASCADE удаляет ArticleSignal обоих версий, но SignalMention специально сохраняются.
Fallback на строках 295–297 снова выбирает v-old, поскольку пустая v-new не оставила mentions.
Отвергнутая сущность возвращается в историю и может изменить first_seen/New/variant logic.

`test_empty_latest_extraction_survives_retention` на SQLite с foreign_keys=ON подтверждает
`[]` до удаления и `[('Old Name', 2026-10-16)]` после. Это те же cascade semantics, которые
предусмотрены PostgreSQL schema; новый production-specific defect не предполагается.
Сценарий пока латентный: нужен второй extraction version. Это **остаток F10**, а не новый
отдельный дефект вне области review; исходный A-gpt A04 уже требовал переживающий retention
маркер пустой версии. Named regression test заканчивается до удаления статьи.

**Предлагаемое исправление:** сохранять выбранную успешную версию/пустой результат отдельно от
каскадно удаляемой ArticleSignal либо обеспечить эквивалентную устойчивую к retention семантику.
Добавить delete → recompute к regression test, сохранив требуемую возможность version fallback.

## Ограничения и интерпретация результатов

- F9 migration проверена от predecessor и после create_all **текущих** моделей. Уже stamped
  `b6d1f0a7c3e5` scratch DB со старым определением таблиц автоматически не обновится от редактирования
  того же revision; раздел 9 dry-run прямо описывает rebuild такой scratch DB. Совместимость
  обновления ранее установленной старой версии этого premerge revision здесь не подтверждается.
- F18 summary остаётся untrusted JSON data, не создаёт новые роли/messages; grounding не принимает
  имя только из отброшенного short body. Это проверка envelope/синтаксиса, а не доказательство
  устойчивости модели к любому prompt injection. Provider не вызывался; известная способность
  instruction-shaped цитаты пройти синтаксическую проверку не объявляется новым дефектом.
- Phase 7 numbers прочитаны и сопоставлены, но не пересчитаны из scratch dataset: после финального
  F19 решения задокументированы displayed 34/0/6 (85% OK, 0% BAD), uncapped 42/2/15, recall 34/42.
  Строгая story membership 89% принята координатором; hidden Maka/Blueprints AI остаются в записи.
  Эти данные не опровергают независимые контрпримеры выше и не являются результатом новых paid calls.
- Реальный production rollback/deploy, concurrent DDL race и многочасовой systemd timeout не
  запускались. Для web проверены TestClient и исполнение JS с stub DOM; новый визуальный browser
  review не проводился, поскольку изменение касается поведения загрузки, а не layout.
- Временные probes и baseline-копии оставлены в `/private/tmp`; главный worktree сохранён.
  Их выводы и достаточные для повторения сценарии записаны выше, поскольку `/tmp` не постоянный архив.

**Merge after fixes:** устранить V01–V04 и закрыть остаток F10/V05, затем проверить эти сценарии
вместе с существующими gates. В рамках этого задания код не исправлялся.
