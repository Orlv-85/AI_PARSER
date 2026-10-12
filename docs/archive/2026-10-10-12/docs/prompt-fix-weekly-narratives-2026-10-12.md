# Исправить weekly explanations и обновить отчёт без повторного расчёта корпуса

Работай в `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` или отдельном worktree.
Общение по-русски, продуктовый текст по-английски. Прочитай AGENTS.md, RTK.md,
weekly trend-spec/validation и текущий код narrative, provider adapter, frozen runner,
публикации и тесты. Все новые промпты сохраняй в файлы и выдавай ссылки.

## Цель и границы

Получить содержательные, подтверждённые источниками English explanations для
weekly report за 2026-10-11. Исправить конкретные причины полного перехода на
templates и применить исправление к уже рассчитанному результату. Это одна
задача: диагностика, минимальный ремонт, проверка реальными JEV/DeepSeek-вызовами,
PR/release при необходимости и новая ревизия отчёта на сайте. Не останавливайся
после написания механизма или очередного промпта восстановления.

Пользователь уже поручил merge/tag предыдущей версии другой сессии. Сначала
проверь актуальные origin/master, PR #23, release, production image и target
publication. Не работай параллельно в её ветке/index и не запускай конкурирующий
deploy. При ещё идущей публикации выполняй независимую локальную работу; перед
своей публикацией сверь точную текущую ревизию. Отталкивайся от фактически
доставленного кода, не предполагай, что старый worktree HEAD равен master.

Не повторяй admission/classification/event clustering 932 статей. Даты, taxonomy,
assignments, cohort, вычисленные counts/metrics/topic states и quality gates
сохраняются. Unknown coverage не лечится улучшением прозы: New/Up/Down остаются
неподтверждёнными. Narrative должен объяснять доступные события и факты; изменение
внимания, причины спроса/выручки/внедрения нельзя выдумывать.

JEV/DeepSeek для этой работы разрешены. Пользователь просит не тратить время
Codex на сметы, обзоры тарифов и повторные общие согласования расходов. Сохраняй
автоматические usage/journal, ограниченные retries и безопасный resume; итоговый
расход сообщи одной строкой. Текстовую обработку выполняют модели, Codex проверяет
код, агрегаты, контракты и ограниченные примеры.

## Готовые результаты

Предыдущий checkout: `/private/tmp/ai-parser-weekly-stage2-20261012`.
Прочитай оттуда либо из актуального master:
- `docs/weekly-stage-3-result-2026-10-11.md`;
- `docs/weekly-stage-2-pipeline-2026-10-11.md`;
- итог этапа 4, если он уже появился.

Private root:
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage3-20261011-manifest-v4-r4`.
Есть candidate.json, candidate-preview.md, frozen.json, narrative-review.json,
journal.sqlite3, weekly.sqlite и candidate-verification.json. Candidate SHA256:
`750be9c70ceffb88890c5557fd651c609451a344ddb7800a35fd936c74aac7ba`.
Все 932 Article учтены, 25 тем находятся в other_signals; все они имеют
insufficient_evidence. Narrative mode — template. Исходный root сохранить.

Восемь ранее выбранных narrative:
- agent-tooling, enterprise-agents, robotics, open-models: local input cap;
- language-models: incomplete completion;
- safety, security, coding-agents: complete JSON, но claims пустые.

Это проверено replay из сохранённых данных. Root cause пустых claims ещё не
доказана. Четыре oversized packet были отклонены локально, поэтому не называй
их отказами DeepSeek. Остальные 17 тем раньше не выбирались для narrative;
их template сам по себе не является provider failure.

На момент проверки:
- входной cap 16000, но `_post()` сравнивает с ним длину сериализованного JSON
  в символах, не измеренные provider tokens;
- output cap 1200; evidence может содержать шесть excerpts по 2000 символов;
- модель должна вернуть claims с точными quotes и отдельно explanation,
  побайтово равный объединённым claims;
- одинаковый narrative prompt используется для подтверждённых направлений и
  insufficient_evidence; JEV support question тоже упоминает direction;
- explain() сводит многие причины к False, после чего worker оставляет template;
- generic deepseek cache сохраняет parsed JSON до полной narrative validation.

## Последовательность работы

1. **Воспроизведи причины на существующих восьми packet.** Получи агрегаты размеров
   system/user/body, доли evidence/metadata, request limits, finish_reason, формы
   schema и точного validation failure. Сопоставь каждый narrative с request/cache
   key. Не печатай private тексты/ответы/секреты. Проверь, содержат ли выбранные
   excerpts реальные факты, а не преимущественно навигацию/введение. Проверь
   обязательные поля, quote/reference IDs, ограничения чисел, English и возможное
   противоречие prompts для insufficient_evidence. Недоказанные причины обозначай
   гипотезами и проверяй ограниченным targeted model call.

2. **Исправь пакет и контракт ответа.** Построй ограниченный narrative packet:
   нужные topic/state/quality fields и содержательные исходные excerpts, выбранные
   из уже сохранённого evidence с устойчивыми ID и привязкой к source. Учитывай
   размер полного запроса и резерв для instructions/schema/escaping. Не обрезай
   JSON посередине и не теряй цитируемые факты ради случайного среза. Расширять
   excerpts допускается только из существующих проверенных source texts, без
   изменения evidence identity и метрик. Точные новые spans должны иметь proof.

   Не повышай глобальные classification caps как побочный способ починить prose:
   это может инвалидировать совместимый cache корпуса. При необходимости введи
   отдельные разумные narrative input/output caps и narrative prompt version.
   Output должен вмещать небольшой законченный English текст и evidence claims.
   Рассмотри сборку explanation кодом из прошедших проверку claims, чтобы модели
   не требовалось дважды точно воспроизводить один текст. Сохрани совместимость
   публикуемого API и содержательные проверки.

   Для insufficient_evidence явно запроси описание конкретных событий по теме
   в выбранной неделе, с кратким сравнением имеющихся фактов при наличии оснований.
   Не требуй доказанного направления и не запрещай фактический обзор только
   потому, что trend не подтверждён. Ограничение coverage должно быть видно,
   но не заменять собой весь полезный текст. Направление/числа из калькулятора
   и факты из статей проверяются по своим источникам; модель не изобретает метрики.

3. **Исправь validation, причины fallback и resume.** Сохрани проверки JSON,
   finish_reason, topic/evidence IDs, literal quotes, English, чисел и JEV support
   >=0.85. Не принимай пустые или неподтверждённые claims ради deepseek mode.
   Различай pre-dispatch input size, output truncation, пустые claims, malformed
   schema, failed support, реальное отсутствие evidence и временную provider
   ошибку. Причина должна сохраняться по topic, а общий narrative_mode честно
   отражать selected successes/fallbacks. Run-budget pause не объявляй успешным
   завершением всей prose-работы.

   Ограниченная исправляющая попытка после подтверждённой технической ошибки
   допустима; успешные narratives не повторять. Старый пустой cached JSON не должен
   вечно побеждать исправленный prompt: task/version key должен это различать.
   При transient failure используй уже реализованный reviewed recovery; исправь
   узкий дефект при необходимости и продолжи в той же сессии. Не сбрасывай журнал.

4. **Проверь реальными моделями именно восемь провалившихся narrative.** Сначала
   несколько случаев, охватывающих oversized/truncated/empty-claims, затем все
   восемь на проверенном механизме. Получи содержательный English текст с фактами
   и источниками, не только перефразированное «10 to 15, trend unconfirmed».
   Для настоящего отсутствия доказательств сохрани честный fallback с конкретной
   причиной. Не расширяй этот ремонт до новых классификаций всего корпуса или
   обязательной генерации текста для всех 25 тем. Покажи 2–3 ограниченных примера
   before/after и полный агрегат результата 8/8: accepted, held и причины.

5. **Сохрани отдельную narrative revision и доставь её.** Создай проверяемую lineage
   от r4, сохрани прежний candidate и paid artifacts. Поддержи повторный запуск
   новой процедуры без повторных model calls. Не редактируй candidate вручную
   как неподписанный JSON и не обходи frozen code/payload проверки publisher.
   Новая ревизия должна иметь валидный payload/hash/provenance. Проверяемо сохрани
   admission, assignments, даты, event IDs, denominators, cohort, counts/metrics,
   состояния тем и quality facts; меняются только prose, её evidence-support
   metadata, diagnostic fields и необходимые revision/lineage fields.

   Добавь регрессии для выявленных причин, cache/version reuse, unsupported
   claims, сохранения метрик и provider-free publication новой ревизии. Пройди
   dev-quality-gate, создай PR от актуальной базы, дождись CI и доведи исправление
   до штатного release и новой публикации за 2026-10-11. Перед заменой сделай
   private backup текущей версии и проверь concurrent drift. Если другая сессия
   ещё публикует предыдущую версию, не соревнуйся с ней за publication pointer.
   Проверь API и существующую страницу: новые English explanations, источники,
   реальные narrative modes/reasons и неизменные trend metrics/statuses.

## Тесты и завершение

Все pytest-прогоны уже разрешены пользователем. Для другого venv/env используй:
`rtk proxy /Users/vyacheslavorlovskiy/.codex/bin/run-pytest --python ./venv1/bin/python --env NAME=VALUE -- <pytest arguments>`.
Это разрешение только для pytest; сохраняй изоляцию тестовых БД. Если managed
runtime блокирует доступ, объясняй конкретное ограничение, не спрашивай заново,
разрешает ли пользователь тесты.

Не включай weekly scheduler, не меняй daily/auth/retention 800/thresholds 5/4 GiB,
не переписывай другие отчёты и не запускай восстановление исторического coverage.
Не скрывай существующее insufficient_data под новыми красивыми explanations.

Сохрани `docs/weekly-narrative-repair-results-2026-10-12.md`: доказанные причины,
исправления, результат по восьми темам, 2–3 before/after, неизменность метрик,
проверки/commit/PR/release/report revision/URL, private lineage/backup paths и
одну строку расходов. Если fallback сохранился, укажи точную причину, а не общий
«DeepSeek не смог». Критерий результата — проверенные содержательные narratives
на реальных packet и их корректное отображение, а не только зелёные mock tests.
