# Spec Intake Seed

Use this document as authoritative feature intake input when drafting/updating 
the feature specification.

- Title: Weekly AI Analytics for management dashboard
- Problem: Нет единого управленческого обзора AI-рынка за неделю: новости разрознены, тренды и динамика не видны.
- Users: CEO, COO, CPO, Head of Product, руководители направлений
- In scope: Еженедельная выборка новостей за 7 дней; передача набора в Antigravity; отчет New/Trending Up/Trending Down + summary; новый раздел в web UI + переход
  с главной
- Out of scope: Изменение логики основного фетчера; редизайн всей админки; прогноз >1 недели; ручная модерация каждой новости
- Acceptance: С главной есть переход в Weekly AI Analytics; отчет строится по последним 7 дням; есть блоки New/Trending Up/Trending Down и менеджерский summary
- Constraints: Зависимость от Antigravity API; таймаут генерации до 60с; не ломать текущие API и страницы
- Non-functional: Открытие страницы до 2с без генерации и до 60с с генерацией; понятная обработка ошибок; логирование запросов и ошибок
- Risks: Шумные выводы модели; смягчение: строгий промпт, ограничение источников, пост-валидация формата
- Definition of done: Раздел доступен с главной; аналитика за неделю через Antigravity; критерии приемки покрыты тестами; lint/pytest зеленые

Source artifacts:
- /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/feature_intake/20260314T091051Z_weekly-ai-analytics-for-management-dashboard_98434/intake.json
- /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/feature_intake/20260314T091051Z_weekly-ai-analytics-for-management-dashboard_98434/intake.md
