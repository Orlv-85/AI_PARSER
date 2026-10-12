> **ARCHIVE — historical record, 2026-10-10–12.** Saved prompts, approvals, commands and runtime states are superseded; do not use this file to resume work. See the [archive index](../README.md) for completed outcomes and remaining work.

Продолжи в той же feature-ветке после завершённого re-enrichment.
Прочитай AGENTS.md, RTK.md и docs/reenrich-production-results-2026-10-11.md.
Разовая обработка production выполнена, её не нужно запускать снова.
Теперь доведи обычный ежедневный сбор и публикацию до согласованного результата.

Подтверждённая read-only диагностика production:
- active cron: fetch `0 1 * * *`, digest `0 2 * * *`;
- сервер использует Europe/Vilnius, сейчас UTC+3;
- live scripts/run_daily_digest_job.sh выбирает REPORT_DATE через
  `date -u -d 'yesterday'`;
- запуск в 02:00 локального времени происходит в 23:00 предыдущего UTC-дня;
  последняя запись digest создана 2026-10-10 23:00:16 UTC для report_date
  2026-10-09, хотя пользователь ожидает уже отчёт за 2026-10-10;
- в момент проверки сохранённого digest за 2026-10-10 нет, groups/items пусты;
- в конце /opt/ai-news/logs/daily-digest.log:
  `DeepSeek returned invalid summaries after retry; digest was not published`
  затем `DeepSeek unavailable; using source text excerpts (not AI summaries)`;
- у ошибок старого локального provider proxy в том же логе другая история;
  не приписывай их последнему DeepSeek-вызову без связи по запуску/времени;
- новый pipeline уже содержит исправления publication semantics, но
  CATEGORY_CRITERIA ordinary JEV пока содержит старые 7 категорий;
  новый REENRICH_TOPIC_ORDER отдельно делает 10 категорий readable/filterable;
- daily digest generator пока использует прежние категории и отдельные
  DeepSeek-запросы без интеграции нового проверенного enrichment-кэша.

Сначала перепроверь состояние: другой процесс мог уже поменять код/production.
Пользователь явно хочет ежедневную автоматическую обработку новых статей,
а не только ручное исправление старых. Продолжение и платные JEV/DeepSeek
в рамках задачи разрешены; не повторяй бюджетные/общие approval-паузы.
Сохраняй ограниченный объём запросов, usage/cost и кэш; это не разрешение
на бессрочные/бесконечные запросы, weekly или архивный crawl.

Необходимый результат:
1. Согласуй время fetch/publication и UTC-день отчёта. Учитывай поддержку
   timezone используемым scheduler и DST; одного TZ=UTC внутри команды
   недостаточно, чтобы изменить момент запуска cron. Не меняй глобальный
   timezone сервера ради приложения. Покажи какой UTC-день обрабатывается
   каждым реальным scheduled запуском.
2. Подключи извлечение достаточного исходного текста и дат новых статей,
   admission плюс согласованную 10-topic категоризацию и Comparison metadata.
   Используй подтверждённую рубрику после пилота, versioned cache и
   conservative handling для недостаточного evidence. Сохрани mandatory
   admission, rejects и поведение provider outage.
3. Для accepted статей сделай сохранение grounded English summary через
   DeepSeek и reuse при публикации. Используй существующий journal/cache,
   не вызывай модель второй раз ради одного и того же summary. Выделение
   HTML/text/date metadata выполняется кодом; Codex получает агрегаты и
   ограниченные примеры, не полный корпус.
4. Daily digest использует готовые summaries, категории и типы из нового
   процесса. При недостаточном evidence или сбое не выдавай сырые excerpts
   за успешно обработанный AI digest. Сохраняй уже опубликованный хороший
   отчёт, записывай точную причину ошибки и позволяй безопасный resume.
   Обоснуй изменение текущего fallback и явно покажи новое поведение.
5. Устрани причину invalid summaries: проверь реальные strict validation
   ограничения (coverage, length, JSON, finish_reason и grounding). Не
   выключай содержательную проверку ради зелёного статуса. Не публикуй
   сырой provider response или секреты в logs/Git.
6. Проверь полноту daily scope. Сейчас limit=200 может обрезать день:
   используй подходящий pagination/обоснованный лимит или явно фиксируй
   coverage. Не объявляй весь день обработанным по первому batch.
7. После исправлений обработай и опубликуй корректный digest за 2026-10-10
   по актуальным cleaned данным. Сохрани прежний отчёт, если он появился,
   в private backup. Самостоятельно остальные frozen/historical отчёты
   не переписывай. Проверь опубликованные English summaries и группы по API
   и странице https://5kzt.l.time4vps.cloud/?date=2026-10-10.
8. Закрепи выполненный re-enrichment и эти исправления в commit/PR и
   штатном release, чтобы локальный production image ai-news-reenrich:20261011
   с новой миграцией не был потерян при следующем deploy. Preserve user files.
   Перед commit/push: dev-quality-gate, полный make lint/pytest с venv1 и
   file-backed isolated SQLite, необходимые PostgreSQL проверки. Не
   используй production как тестовую БД. Не скрывай skipped tests.

Не останавливайся на написанном механизме. Итог должен быть установлен на
production, cron должен использовать актуальные код/образ, целевой digest
должен быть опубликован, а весь обычный scheduled путь подтверждён.
Не называй ручной запуск доказательством успешного автоматического запуска:
покажи effective schedule/command и результат реального scheduled исполнения
или честно укажи, что оно ещё не наступило.

Weekly flag и weekly cron off, retention 800, thresholds 5/4 GiB сохраняются.
Сохрани итоговый report: commit/PR/release/image/migration, schedule и UTC-day,
counts/coverage, usage/cost, backup/cache paths, provider errors, проверки
сайта и подтверждение автоматической публикации. Секреты не печатай.
