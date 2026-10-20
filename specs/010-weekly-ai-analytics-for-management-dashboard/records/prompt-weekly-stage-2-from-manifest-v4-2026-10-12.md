# Weekly report: этап 2 по завершённому manifest v4

Выполни только этап 2: подготовить и проверить weekly pipeline для расчёта отчёта за 2026-10-11 на готовом входе. Этап 1 уже завершён, повторный production export и новая общая диагностика не нужны.

Прочитай:
- AGENTS.md и /Users/vyacheslavorlovskiy/.codex/RTK.md;
- specs/010-weekly-ai-analytics-for-management-dashboard/records/weekly-report-stages-2026-10-12.md;
- specs/010-weekly-ai-analytics-for-management-dashboard/records/weekly-stage-1-input-2026-10-11.md;
- specs/010-weekly-ai-analytics-for-management-dashboard/records/prompt-weekly-stage-2-pipeline-2026-10-12.md;
- актуальные trend-spec, trend-plan, trend-validation и соответствующие код/тесты.

Этот промпт уточняет исходное задание этапа 2 по фактическим результатам этапа 1. Цель и общие ограничения четырёх этапов сохраняются. Выполняй последовательно, без запуска этапов 3/4.

## Готовый вход

Private root: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage1-20261011/`.
Используй `snapshot.json`, **`selection-manifest-v4.json`**, `source-evidence.json`,
`published-target.json`, `handoff-receipt.json`. Перед чтением данных проверь file hashes
по публичному handoff; старые manifest v1/v2/v3 не использовать.

Не смешивай SHA256 bytes файлов, source fingerprint с JSON spaces и compact weekly
cache fingerprint. Не изменяй исходные артефакты. При отдельном worktree обращайся
к этому абсолютному private root; не добавляй snapshot/bundle/journals в Git.

Этап 1 зафиксировал production v0.1.86, но local HEAD был b5a4d74. Перед работой
проверь актуальный origin/master и состояние другой сессии. Создай отдельную
feature-ветку/worktree от актуальной базы, не продолжай разработку на ветке
архивирования. Нужные незакоммиченные публичные handoffs перенеси отдельно и
проверь их содержимое; чужую работу не перезаписывай.

## Подтверждённые факты

- Учтены все 5 993 Article. В выбранных 35 днях доказана неделя для 932 записей:
  W0 266, W1 158, более ранние недели 95/199/214.
- Из них 114 имеют совместимый accepted admission; 818 остаются unresolved:
  630 без совместимого admission, 187 с negative assessment, один disagreement.
  Не объявляй все 932 допущенными и не удаляй unresolved из учёта молча.
- 26 календарных дат имеют неоднозначную границу недели. 14 из 114 пригодных
  кандидатов имеют week-safe date-only evidence, но не точный UTC day.
- Unassigned pool 2 350, включая 738 normalized timestamps без достаточной
  исходной precision. Заполнение даты одним флагом или discovered_at запрещено.
- Runtime возвращает stale dates/text и observations удалённых rejects.
  Точные группы/IDs и tombstone evidence есть в manifest.
- Ни один comparable publisher cohort для этих недель не доказан. New также
  не имеет полной подтверждённой истории. Этап 2 не может исправить отсутствие
  исторических доказательств изменением thresholds.
- Есть 154 условно совместимых старых assignment keys, но ноль уже доказанно
  совместимых с выбранным проверенным source input и admission. Не обещай reuse
  до проверки полного ключа; не импортируй старые даты/event IDs/eligibility.

## Работа и проверки

1. Исправь freeze/worker: актуальные Article и date/admission evidence определяют
   вход; stale observations сохраняются как история, но не подменяют его.
   Исключи orphan/reject observations. Отсутствие weekly observation не делает
   подтверждённую Article автоматически legacy_unverified.
2. Сохрани честную точность времени. Для week-safe calendar inputs определение
   недели не означает знания UTC day. Не допускай выдуманного day-support и
   event matching по synthetic midnight; при невозможности достоверного расчёта
   сохрани материал в фактах с соответствующими ограничениями.
3. Сохрани наблюдаемые counts/evidence при пустом comparable cohort отдельно
   от недоступных normalized trend metrics. Не показывай отсутствие cohort как
   ноль реальных событий. Подтверждённые New/Up/Down остаются под quality gates;
   используйте существующие insufficient_evidence и quality fields. Не меняй
   методологию и UI ради непустых карточек.
4. Подготовь изолированный runner/команду на frozen input, новую ревизию, durable
   budget/journal/resume и проверяемый import только совместимых decisions.
   Mandatory admission сохраняется; источник незакрытых admission должен быть
   явно предусмотрен в команде этапа 3. Provider failure не должен исчезать из
   denominator или превращаться в semantic rejection.
5. Проверь реальные регрессии через synthetic fixtures и агрегированные private
   проверки: stale conflict dates, deleted rejects, неизвестные/normalized даты,
   calendar boundaries, исправленные июнь/июль Article 95681/95682 вне окна,
   полный scope, exact-key reuse, budget/resume и факты при unknown coverage.
   Private corpus в committed tests не копируй.
6. Пройди dev-quality-gate с venv1 и изолированными SQLite/PostgreSQL. Создай
   commit и reviewable PR с исправлениями и публичным handoff этапа 1, планом
   этапов и относящимися к ним промптами. Стадируй точные пути; исходные private
   артефакты и посторонние файлы в PR не включай. Самостоятельный PR только ради
   read-only этапа 1 не нужен. Не merge/deploy на этапе 2.

## Handoff

Сохрани `specs/010-weekly-ai-analytics-for-management-dashboard/records/weekly-stage-2-pipeline-2026-10-11.md`: commit/PR, результаты
проверок, входные hashes, конкретная команда этапа 3 с private paths, бюджет и
resume, правила reuse, ожидаемые ограничения отчёта и способ штатной публикации
готового payload без повторного обращения к моделям.

Критерий завершения: проверенный код и воспроизводимая команда готовят расчёт
реального отчёта на manifest v4. Полный платный расчёт — этап 3; публикация и
release — этап 4. Не пытайся на этом этапе устранить все неизвестные даты в БД.
Содержательные проверки при необходимости поручай JEV/DeepSeek в ограниченном
объёме, а не Codex по всему corpus. Сохраняй usage и действующие денежные лимиты.

Все новые промпты для других сессий сохраняй в файл и давай ссылку.
