> **ARCHIVE — historical record, 2026-10-10–12.** Saved prompts, approvals, commands and runtime states are superseded; do not use this file to resume work. See the [archive index](../README.md) for completed outcomes and remaining work.

Работаем в /Users/vyacheslavorlovskiy/GitHub/AI_PARSER.
Прочитай AGENTS.md, RTK.md и отчёт:
docs/semantic-admission-production-activation-2026-10-10.md
Промпт продолжает существующую работу. Сохрани чужие изменения.

Цель пользователя: очистить ранее сохранённые статьи от не-AI и неновостного
мусора, используя JEV. Пользователь теперь разрешил JEV-проверку старых записей
и удаление подтверждённого мусора. Прежний запрет на эти действия заменён именно
для этой очистки. Weekly и исторические аналитические прогоны остаются отключёнными.
Этот промпт не разрешает DeepSeek, новую weekly-аналитику или обход архивов сайтов.

Текущий отбор PR #13 проверяет только кандидатов, которых нет в articles.
Он не очищает существующую БД. После первого production-цикла 8300 -> 9146 articles;
846 новых articles получили accept, 437 reject и 186 unresolved не вставлялись.
В ledger осталось 1366 pending кандидатов, которых нельзя считать старыми articles.
Это снимок на 2026-10-10 21:55 UTC; перед работой получить актуальное состояние.

Что сохранять:
- AI-новости, релизы, исследования и политика AI;
- содержательные AI-обзоры, tutorials и evergreen-руководства.
Что исключать: non-AI, incidental AI mentions, рекламные landing pages, About,
навигацию и другие явно non-editorial страницы.
Старая или неизвестная дата, низкий rank, отсутствие категории и старый keyword
score сами по себе не являются причиной удаления.

Порядок работы:
1. Реализуй проверяемый инструмент в отдельной ветке/PR, без попутных изменений UI.
   Изучи src/app/core/jev.py, core/admission.py, storage/admission.py,
   storage/non_news_cleanup.py, scripts/non_news_cleanup.py и их тесты.
   Старый non_news_cleanup умеет только dry-run/backup; deletion там не реализован.
   Его EXPORT_TABLES не включает новые admission_decisions/collection_status.

2. Зафиксируй консистентный production-снимок и точный набор article IDs.
   Основной набор: существующие articles без подтверждённого accept по текущим
   evidence/model/policy/prompt. Уже проверенные 846 не отправлять в JEV повторно,
   если доказательства не изменились. Проверять всю согласованную старую выборку,
   а не только статьи одной недели или прежние 313 URL-кандидатов.
   Для оценки использовать сохранённые title/summary/content. Без нового crawl.

3. Применяй предварительный фильтр и существующую семантическую политику JEV.
   Не подменяй её порогом старого ai_relevance_score. Для destructive cleanup
   отдели подтверждённый reject от неоднозначного ответа: ambiguous/insufficient
   evidence/invalid response/provider failure сохранять, не удалять.
   Определи и обоснуй консервативное правило уверенности для удаления. Не считай
   прежние обсуждения числовых порогов готовыми требованиями и не выдавай
   model confidence за гарантию корректности. Покажи причины и примеры решений.

4. Перед массовыми запросами сообщи объём и оценку стоимости. Общий бюджет этой
   очистки пользователем не задан: прежние $2 относились к другому pilot.
   Реализуй ограничение расходов/запросов и возобновление. Если нужен конкретный
   денежный лимит, запроси только его, продолжая offline-разработку инструмента.
   Сохраняй успешные решения и фактические usage/cost, если provider возвращает их.
   Не повторять оплаченные оценки после перезапуска; bounded evidence, model,
   policy и prompt должны входить в ключ кэша. При сбое JEV остановить проход,
   сохранить прогресс и оставить непроверенное без удаления. DeepSeek не вызывать.

5. Составь dry-run manifest: article ID, canonical URL/hash, evidence hash,
   решение, причина, уверенность/основание, версия модели/правил и зависимости.
   Обязательно учесть article_aliases, digest items/groups/reports, legacy weekly,
   weekly observations/decisions/jobs/snapshots/publications и admission ledger.
   Удаление articles не удаляет скопированные URL/тексты из опубликованных отчётов.
   Явно отрази, где ссылки останутся; не переписывать автоматически целые отчёты,
   narrative, метрики или frozen snapshots. Связанные неоднозначные изменения
   вынести отдельно, сохранив возможность завершить очистку articles.

6. До DELETE сделать закрытый backup и проверить targeted restore на изолированной
   БД. Restore не должен стирать новые данные, поступившие после snapshot.
   Удалять только точные подтверждённые IDs из manifest, с повторной проверкой
   evidence hashes и зависимостей в транзакции. Изменившиеся строки пропускать
   или оценивать заново. Соблюсти FK-порядок, не применять широкие date/score DELETE.
   При rollback не оставлять частично удалённые статьи или потерянные ссылки.

7. Сохранять reject-решения совместимо с admission cache, чтобы следующий fetch
   не вставил тот же мусор обратно. Проверить обработку pending для этих же URL:
   старый pending не должен обойти reject или постоянно запускать новую оплату.
   Сохранить обычный сбор и его обязательный admission; изменения production-данных
   координировать с активным collector, не отключая weekly-защиту.

8. После успешных тестов, manifest и проверенного restore выполнить удаление
   подтверждённого мусора в рамках разрешения пользователя. Не останавливаться
   просто на описании инструмента или dry-run. Если удаление нельзя выполнить
   безопасно, назвать конкретную причину и уже подготовленный набор, а не считать
   очистку законченной. Не запрашивать повторно общее разрешение использовать JEV
   или удалить подтверждённый мусор: пользователь его уже дал.

Проверки offline и на изолированной БД:
- AI-новость, research, substantive tutorial/guide сохраняются;
- clear non-AI/landing/About исключаются; ambiguity и неизвестная дата сохраняются;
- повтор/возобновление не оплачивает одинаковый verdict повторно;
- outage не превращается в reject; budgets корректно останавливают проход;
- FK, rollback, concurrent row changes, targeted restore и idempotent apply;
- digest/snapshot references отображены в manifest;
- следующий обычный fetch не возвращает удалённый reject;
- accepted articles с текущим кэшем не переоцениваются без изменения evidence.

Перед commit/push: dev-quality-gate, полный make lint и pytest.
Для операций DELETE/restore нужны PostgreSQL-проверки на изолированной БД;
SQLite-only результат не доказывает production FK/transaction behavior.
Не использовать production как тестовую БД. Если PostgreSQL-проверка недоступна,
указать блокировку до destructive apply и подготовить остальные артефакты.

Итог сохранить в файлы: PR/commit, snapshot и manifest hashes, checked/kept/rejected/
unresolved/failed/deleted counts, стоимость JEV, backup/restore paths, затронутые
зависимости и ограничения очистки. Проверить сайт и обычный admission после apply.
Не печатать секреты. Weekly flag false и cron отключён сохранить.
