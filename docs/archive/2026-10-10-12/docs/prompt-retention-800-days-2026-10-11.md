> **ARCHIVE — historical record, 2026-10-10–12.** Saved prompts, approvals, commands and runtime states are superseded; do not use this file to resume work. See the [archive index](../README.md) for completed outcomes and remaining work.

Продолжаем текущую очистку. Дополнительное требование пользователя:
увеличить стандартный срок хранения articles со 100 до 800 дней.

Согласуй defaults в scripts/db_maintenance.sh, scripts/deploy_prod.sh и
src/app/cli/main.py (prune --older-than-days). Обнови README и необходимые
проверки. Сохрани явные пользовательские overrides RETENTION_DAYS и CLI.
Проверь production cron/workflows на явно заданные 100 дней: итоговый срок
должен быть 800 и сохраняться после следующего деплоя. Не делай глобальную
замену числа 100: оно используется и для других целей.

Порог DB_MAX_SIZE_GB=5 и DB_TARGET_SIZE_GB=4 остаются прежними.
Weekly и его cron остаются выключенными. Сам prune ради этой настройки
не запускай. Увеличение retention не восстанавливает удалённые статьи.

Продолжай согласованную очистку через JEV; настройка retention не заменяет её.
Перед commit/push выполни dev-quality-gate: полный make lint с venv1 и pytest
на отдельной файловой SQLite. В отчёте укажи effective production retention
и места, где настройка закреплена.
