> **ARCHIVE — historical record, 2026-10-10–12.** Saved prompts, approvals, commands and runtime states are superseded; do not use this file to resume work. See the [archive index](../README.md) for completed outcomes and remaining work.

Задача завершена и применена в production. Актуальный отчёт:
docs/reenrich-production-results-2026-10-11.md.
5270 строк обновлены, 1467 подтверждённых rejects удалены, 406 материалов обогащены.
API, backup и PostgreSQL 14/18 apply/rollback/restore проверены.
Кэш и оплаченные ответы не повторять. Спорные случаи сохранены для просмотра.
Ниже — исторический prompt до массового прохода; его бюджетные остановки
заменены явным разрешением пользователя на массовую обработку и применение.

Продолжаем в /Users/vyacheslavorlovskiy/GitHub/AI_PARSER.
Прочитай session-context-reenrich-2026-10-11.json и docs/reenrich-rubric-validation-2026-10-11.md.
Уточнение admission/категорий и адресная JEV/DeepSeek-проверка завершены; кандидат — pilot-rubric-clarification-3.
Из прежних 13 без категории: 9 получили согласованные темы, 1 — non_ai, 3 остаются без темы.
Все 9 положительных контролей и 3 прежних reject-кандидата сохранены; 5 admission-расхождений требуют просмотра.
Пороги прежние. Общий usage-priced расход $0.196297; накопительные лимиты пилота $1.50 (JEV $0.25 / DeepSeek $1.25) уже подтверждены, повторно их не спрашивай.
Используй готовый кэш tmp/reenrich-2026-10-11 и общий pilot-journal.sqlite3: URL не скачивать повторно, успешные оплаты/summaries не повторять, корпус не выводить.
Предпочитай DeepSeek для обработки текстов; не останавливай работу ради мелких платных вызовов в согласованном бюджете.
Следующий этап — подготовка массового прохода с кандидатом v3; массовый денежный лимит ещё не согласован.
Production не менялся. Weekly off, retention 800, удалённые статьи не восстанавливать; сохраняй остановки между крупными этапами.
