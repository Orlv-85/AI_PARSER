# Prompt: feature doc for the fetch pipeline before refactoring (2026-10-20)

Репозиторий `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Прочитай `AGENTS.md` целиком, особенно "Feature Docs Next To Code", "Specs" и "Prompts For Other
Sessions". Работай в отдельном git worktree от `origin/master`: в основной папке могут работать
другие сессии.

## Зачем

Перед рефакторингом крупных модулей сначала пишется описание фичи рядом с кодом (подход Carson
Gross, "Markdown in /src"). Оно фиксирует, что модуль должен делать сейчас, и для каждого правила
называет тесты. Это страховка рефакторинга: явный список того, что не должно измениться, плюс видно,
какие правила тестами не покрыты.

Эта сессия делает только описание для приёма новостей: `src/app/core/pipeline.py` (1717 строк, нет
module docstring) и то, что он вызывает. Код не меняется (кроме строки в docstring), рефакторинга
нет.

## Эталон

`src/app/core/daily_signals.md` - формат: header `<!-- code-doc ... -->`, Behavior (правила, не
числа: числа по имени константы; Mermaid-схема потока; у каждого правила `Tests: ...`, правило без
теста помечено), Decisions (решение и почему, 1-2 строки, без истории), Invariants (тоже с тестами),
Code map (flow, modules, tables, versions/flags, where to change what), Tests.

## Шаги

1. Прочитай `src/app/core/pipeline.py`, `src/app/ingest/*.py`, `src/app/core/{admission,jev,dedup,canonicalize,scoring}.py`,
   `src/app/storage/admission.py`, вызывающие места (`cli/main.py`, `web/service.py`, `scripts/run_daily_fetch_job.sh`)
   и тесты, которые их покрывают (`grep` по именам в `tests/unit/`).
2. Источники для Decisions: `specs/001-ai-news-collector/`, `specs/002-fetch-pipeline-optimization/`,
   `specs/011-json-source-intake/`, `docs/archive/2026-10/semantic-admission-*`, `docs/configuration.md`,
   `git log -- src/app/core/pipeline.py`. Не придумывай причины: если причина решения не найдена,
   пиши "why: unknown" и вынеси вопрос владельцу.
3. До написания предложи владельцу границы описания (`covers`) и остановись за ответом:
   один документ `src/app/core/pipeline.md` на pipeline + ingest + admission, или отдельный
   `src/app/ingest/<...>.md` для парсинга. Учти: CI требует обновлять описание при любом изменении
   файлов из `covers`; общие `storage/repos.py` и `storage/models_sql.py` в `covers` не включать.
4. Напиши черновик описания. Для каждого правила Behavior проверь по коду теста, что тест
   действительно проверяет это правило (не по имени теста).
5. Добавь в module docstring `pipeline.py` строку `... : pipeline.md next to this file.`, зарегистрируй
   описание в `docs/README.md` ("Code docs"), `README.md` ("Documentation") и `src/app/README.md`.
6. Проверки: `./venv1/bin/python scripts/check_code_docs.py`, затем `--diff origin/master --strict`
   после коммита; `make lint PYTHON=./venv1/bin/python`; `./venv1/bin/pytest`.
7. Открой PR, не мержи. Описание пишет агент, но курирует владелец: в ответе дай ссылку на PR и
   отдельно список (а) правил без тестов, (б) решений с "why: unknown", (в) мест, где код показался
   противоречивым или мёртвым. Эти списки - вход для решения, что рефакторить первым.

## Не делать

- Не менять поведение, сигнатуры, флаги, настройки, деплой.
- Не трогать `storage/repos.py`, `web/app.py` (их описания - отдельные будущие сессии).
- Не генерировать описания для других фич.
