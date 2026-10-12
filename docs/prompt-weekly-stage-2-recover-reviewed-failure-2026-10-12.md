# Weekly stage 2: recover an operator-reviewed transport failure

Вернись к этапу 2 только для исправления safe recovery после failed provider request.
Прочитай AGENTS.md, RTK.md, общий weekly plan, handoffs 1/2 и
`docs/weekly-stage-3-result-2026-10-11.md`. Application code нельзя было менять
во время frozen расчёта; stage 3 остановлен без candidate. Новый production export,
общий аудит, старый pilot и публикация не нужны.

Checkout `/private/tmp/ai-parser-weekly-stage2-20261012`, implementation commit
`8743fb00f39c3a4df9f7b1afbbff2253cf790405`, docs HEAD
`dff73d338fcb177b799a2f438896d061351c8745`, PR #23. Сохрани чужие изменения.
Используй venv1, PYTHONPATH=src и shell через rtk.

Private root:
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage3-20261011-manifest-v4-r3`.
Frozen identity:
`614fcdd4c8e81d19686452b653e9e9b478d5e1e089f8ba88e7d235de73eea790`.
В root сохранены frozen.json, weekly.sqlite, journal.sqlite3, usage.json,
stage3-verification.json, checkpoint-review.json и billing-review.json. Сначала
проверь их hashes по stage 3 report; сделай private backup перед любой миграцией.

Один DeepSeek ambiguity request от 2026-10-12 12:01:55 UTC получил ReadError
без ответа/usage. Exact key и Article ID находятся в private review receipt.
Пользователь уже принял неопределённый расход: сверка invoice не является
предусловием продолжения. Повторно спрашивать согласие на эту сумму не нужно.
Учитывай полный резерв $0.005059, actual usage оставляй unknown.
Всего committed $0.074360, known usage-priced $0.069301:
JEV 292 calls, DeepSeek 54 calls (53 responses + один failed).

Recovery gap: PilotJournal.reserve() блокирует state failed/inflight или actual NULL;
PilotJournal.call() блокирует saved entry, если state != response или actual NULL.
Общей review/resume процедуры для network failure нет. Существующие methods
review_quote_failure/review_truncated_summaries относятся к другим pilot outputs.
Read-only воспроизведение safeguard и целостность БД уже проверены. Простой
повтор run не решит проблему. Не удаляй failed row, не выставляй нулевой cost,
не выдумывай provider response/usage/semantic negative и не отключай защиту глобально.

Реализуй узкую, явно аудируемую процедуру operator review для такого случая:
проверенный failed dispatch остаётся в журнале со своим conservative commitment,
unknown actual usage и review provenance; item остаётся unresolved и не теряется
из denominator. После такого review остальные ещё не оплаченные tasks могут
продолжаться. При повторном обращении к reviewed failure не отправляй тот же
оплаченный/потенциально оплаченный dispatch снова и не подменяй ответ успешным.
Обычные unreviewed failed/inflight/missing-usage requests по-прежнему блокируются.

Сохрани все 345 успешных responses и совместимые caches без повторной оплаты.
Frozen code hashes и input identity нельзя молча подменять. Если исправленный
код требует новую frozen revision/root, подготовь проверенный перенос с lineage
и cumulative accounting исходного journal, включая $0.074360. Старый root остаётся
нетронутой историей. Новая ревизия не получает отдельные дополнительные $10:
действуют исходные cumulative caps $10 total / $7 JEV / $3 DeepSeek.
Не импортируй старые conditional keys или stale progress/dates/event IDs.

Полный scope остаётся 932: W0/W1/H2/H3/H4 266/158/95/199/214, calendar 123.
Checkpoint replay: compatible admission 205, rejected 36, pending 691.
Среди admitted: 71 resolved assignments, 41 unresolved, 93 pending.
Это промежуточные counts. Подтверждённого comparable cohort и полной New history
нет; thresholds и UTC precision нельзя ослаблять ради карточек.

Добавь meaningful regressions для reviewed unknown failure, сохранённого резерва,
нулевого network replay этого key, отказа unreviewed failure, cumulative caps,
совместимого успешного cache reuse, failed admission/assignment в denominator
и полного frozen scope. Сначала targeted checks; перед commit/push полный
dev-quality-gate: make lint PYTHON=./venv1/bin/python и ./venv1/bin/pytest
с изолированными БД. Не используй production для тестов.

Устранить local Settings bootstrap issue можно process-local auth configuration
или private минимальным env file без вывода secrets; production auth и основной
.env не менять. Документируй точную проверенную invocation следующего stage 3.

На этом этапе не делать paid continuation, publish, merge, deploy или включение
scheduler/v2 flag. Подготовь проверенный recovery, версия кода, private receipts,
точная resume command и сохранённый новый prompt этапа 3; затем остановись.
Все новые handoff prompts сначала записывай в docs/prompt-<task>-<YYYY-MM-DD>.md,
сохраняй предыдущие, выдавай clickable file link и переносите это правило в context.
