# Weekly report: stage 3 from the verified frozen manifest v4 revision

Выполни только этап 3: расчёт и проверку кандидатного English weekly report за
2026-10-11. Прочитай AGENTS.md, RTK.md, общий план этапов, handoffs этапов 1/2,
`docs/prompt-weekly-stage-3-generate-2026-10-12.md` и актуальные trend documents.
Этапы 1/2 завершены; не повторяй production export, общий аудит или старый pilot.

Используй code commit/PR из `docs/weekly-stage-2-pipeline-2026-10-11.md`, checkout
`/private/tmp/ai-parser-weekly-stage2-20261012`, `venv1` и `PYTHONPATH=src`.
Выполни именно `run` из handoff этапа 2, на private root
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage3-20261011-manifest-v4-r3`.
Сначала проверь five input hashes, frozen identity и code hashes. Артефакт без
суффикса и с `-r2` — ранние superseded подготовки с нулём calls, не вход этого этапа.

Scope: все 932 week-assigned Article, W0/W1/H2/H3/H4 266/158/95/199/214.
110 имеют совместимый admission, 822 требуют JEV admission на выбранном source
text; runner делает это явно до weekly assignment. 123 calendar inputs не имеют
точного UTC day. Два положительных assignment decisions разрешены к reuse по
проверенному полному ключу; 154 старых условных keys нельзя импортировать массово.
Unassigned pool 2350, ambiguous boundaries 26 и outside scope 2685 сохранены в учёте.

Проверь официальные тарифы до dispatch. Frozen caps: $10 total, $7 JEV, $3 DeepSeek
кумулятивно по всем attempts/restarts этой ревизии. Старый $2 pilot не относится
к ней. Общая авторизация JEV/DeepSeek сохраняется. Если нужна иная цена/лимит,
не подменяй frozen input/journal; представь конкретный scope/сумму и сохрани историю.

При обычной остановке на run budget продолжай той же командой/root. Unknown billing,
missing usage и failed requests требуют review; не обнуляй journal и не повторяй
оплаченные dispatch. Все provider failures остаются unresolved, не исчезают из
denominator и не становятся negative semantic decisions. Не меняй код во время
расчёта: воспроизведённый defect вернуть этапу 2, сохранив оплаченные результаты.

Подтверждённый comparable cohort отсутствует, полная New history не доказана.
Не ослабляй thresholds ради карточек. Рассчитай доступные факты/темы, evidence,
English explanations и ограничения через существующие insufficient_evidence/
quality fields. Нельзя придумывать UTC support days или semantic event matches
по calendar midnight. Codex проверяет агрегаты/арифметику/контракты; содержательные
решения делает JEV/DeepSeek.

Проверь `candidate.json`, его full scope, counts/denominators, states, evidence,
English explanations и claim support. Запиши hashes, code commit, calls/tokens/cost,
reuse и ограничения в `docs/weekly-stage-3-result-2026-10-11.md`. Private corpus,
provider responses и credentials не копируй в Git/docs/logs.

Не publish, merge, deploy или включать scheduler/v2 flag. Штатная provider-free
публикация готового payload описана в handoff этапа 2 и относится к этапу 4.
По завершении остановись и передай сохранённый prompt этапа 4. Каждый новый prompt
для другой сессии сначала сохраняй в `docs/prompt-<task>-<YYYY-MM-DD>.md`, сохраняй
предыдущие prompts и давай пользователю clickable file link.
