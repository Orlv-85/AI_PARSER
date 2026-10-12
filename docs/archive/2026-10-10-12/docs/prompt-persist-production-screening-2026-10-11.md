> **ARCHIVE — historical record, 2026-10-10–12.** Saved prompts, approvals, commands and runtime states are superseded; do not use this file to resume work. See the [archive index](../README.md) for completed outcomes and remaining work.

Работаем в /Users/vyacheslavorlovskiy/GitHub/AI_PARSER.
Прочитай AGENTS.md и RTK.md. Создай отдельную ветку и PR.
Сохрани чужие изменения и untracked-файлы.

Задача: закрепить production-настройки, чтобы после следующих деплоев не приходилось
вручную включать семантический отбор и отключать weekly.

Согласованное требование пользователя:
- Production: AINEWS_SEMANTIC_ADMISSION_ENABLED=true и AINEWS_JEV_ENABLED=true.
- Weekly: AINEWS_WEEKLY_V2_ENABLED=false, AINEWS_WEEKLY_CRON_ENABLED=0.
- Ни отсутствующие repository variables, ни старый серверный .env не должны
  случайно возвращать scoring-only или включать weekly.
- При недоступности JEV обязательный отбор останавливает сбор; keyword fallback
  вместо семантического допуска запрещён.

Отбор уже включён вручную на production v0.1.77, PR #13 merged.
Добавь в этот PR существующий untracked-отчёт:
docs/semantic-admission-production-activation-2026-10-10.md
Не переписывай фактические результаты отчёта под новое состояние.

Подтверждённые точки изменения:
- .github/workflows/deploy-release.yml и deploy-by-tag.yml сейчас используют
  weekly fallback 'true'. Они формируют runtime env payload и сливают его с .env.
- docker-compose.prod.yml: JEV/admission fallback false, weekly fallback true.
- deploy/.env.prod.example: weekly true.
- scripts/deploy_prod.sh: weekly cron по умолчанию включён; серверный .env сам
  по себе не экспортирует этот параметр в shell. После PR #13 deploy восстановил
  cron, и его пришлось снова отключить вручную.

Исправь оба deploy-workflow, production Compose, пример .env и deploy script
согласованно. Передавай deploy-time cron setting в процесс, который реально
вызывает deploy_prod.sh. Слияние env должно давать ровно одно значение каждого
управляемого флага и сохранять JEV_API_KEY и другие секреты.
Generic Settings/defaults для локальной разработки можно оставить совместимыми:
пользователь требует включённого production-отбора, а не платных вызовов в тестах.
Не менять daily digest, auth, ports, retention или источники.

Обнови README. Добавь offline-регрессии:
- оба workflow доставляют согласованные флаги, включая отсутствующие repo vars;
- старые server env значения заменяются без дублей и потери секретов;
- production Compose передаёт флаги в web, CLI и cron-команды;
- повторный deploy удаляет managed weekly cron, сохраняя остальные задания;
- версии admission policy/prompt продолжают передаваться;
- при отсутствующем JEV ключе обязательный screening не становится keyword-only.

Ближайшие тесты:
tests/unit/test_deepseek_deploy_workflows.py
tests/unit/test_deploy_cron_image.py
tests/unit/test_semantic_admission_compose.py
tests/unit/test_screening_notice.py

Используй dev-quality-gate перед commit/push:
make lint PYTHON=./venv1/bin/python
./venv1/bin/pytest
Shell syntax проверить bash -n для изменённых shell scripts.
Модели в тестах замокать; PostgreSQL только изолированный.

Создай PR с конкретным описанием поведения и проверок, дождись CI.
Не merge/tag/deploy самостоятельно в рамках этого промпта. Production уже работает;
этот PR должен закрепить настройки для следующих деплоев. Не запускай платные
модели, weekly, очистку или backfill ради проверки deployment settings.
