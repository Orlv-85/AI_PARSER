# Weekly report 2026-10-11: вход и handoff этапа 1

Этап 1 завершён 2026-10-12. Существуют неизменный private production snapshot,
отдельный manifest отбора **revision 4**, source-evidence bundle и verification receipt.
Это подготовка входа, а не готовый weekly report. Полный weekly расчёт не запускался.

Срез БД: **2026-10-12 07:05:40.593561 UTC**, PostgreSQL MVCC `4282:4282:`.
Экспорт выполнен в одной `REPEATABLE READ / READ ONLY` транзакции; runtime freeze
прочитан в той же транзакции. Его `data_cutoff` — `07:05:41.893704 UTC`.
Исторические file caches и журналы сохранены отдельно внутри snapshot; на них
не распространяется транзакционная согласованность PostgreSQL.

## Версии и границы работы

- Production: **v0.1.86**, host commit `f83594a24fa74ce78da8dc8e64eaab8694bd46bc`.
  Image: `ghcr.io/orlv-85/ai-parser:v0.1.86`, image ID
  `sha256:0d98858e39547ade5765a2733176b7cf2475059c9c3541eb4b79fd7139356eac`.
- Local HEAD: `b5a4d744c8e0268b4bb4f1841a6098502308fa81`.
  SHA256 пяти weekly modules (`storage.weekly`, `weekly_worker`,
  `weekly_enrichment`, `weekly_topics`, `weekly_analytics`) совпадают с runtime.
  Hashes сохранены в snapshot; версии не предполагаются одинаковыми целиком.
- Методология `attention-v2.1`, taxonomy `weekly-topics-1`, prompt `weekly-1`;
  JEV `jev-1.13.0`, DeepSeek `deepseek-flash`.
- Weekly flag выключен. Application code, production data, scheduler, daily,
  auth и настройки retention не изменялись. На сервере добавлен только private backup.
  Чужие untracked prompts, preview runner и tests сохранены; branch/index не тронуты.
- Прочитаны актуальные trend spec/plan/validation и реализация. Заголовки старого
  proposed plan не означают отсутствие реализованного weekly engine.

## Private artifacts

Локальный каталог: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage1-20261011/`.
Права каталога `0700`, JSON artifacts `0400`. Corpus/provider payloads остаются
в игнорируемом private `tmp`, в этот документ вынесены только агрегаты и fingerprints.

| Файл в каталоге | SHA256 точных bytes | Назначение |
| --- | --- | --- |
| `snapshot.json` | `9c7f73cde3136a5cc3425e0447adf42b1accae7a63d30706722f8b40a8e5fc00` | Неизменный production export, runtime freeze, старый pilot manifest/cache, receipts |
| **`selection-manifest-v4.json`** | `c9bea6115329a605bb809540d8b591d1975b4268d9e0251ec4929952cb4b033b` | Актуальный отбор, точные ID групп, даты/интервалы, admission refs, tombstones, требования к коду |
| `source-evidence.json` | `4f5ae0b18e7e3d59bfbf23303496b5f401ffaa611073ba8737b14b6660188208` | Копия 5 036 существующих source caches и mass admission evidence |
| `published-target.json` | `12a7772b0db49842906ab15c189a8baeb4eceedd067a4efbea9de0ae5a948a43` | Опубликованный target report отдельно от входа |
| `handoff-receipt.json` | `ec22e8f4bb0e74aa14d74eb6cc43a22275b0534e80c8f1b1cd910d45787ab697` | Проверки, версии, operator script hashes и следующий шаг |

На сервере исходный snapshot сохранён по адресу:
`/opt/ai-news/backups/weekly-stage1-20261011/snapshot-9c7f73cde3136a5cc3425e0447adf42b1accae7a63d30706722f8b40a8e5fc00.json`.
Локальный manifest и source bundle сервером автоматически не импортировались.

Ранние `selection-manifest.json`, `selection-manifest-v2.json` и
`selection-manifest-v3.json` сохранены для аудита, но **не являются входом этапа 2**.
Revision 4 учитывает различия форматов source/weekly fingerprints, точность
нормализованных дат, условность reuse и доказательства удалённых rejects.

Для чтения достаточно snapshot + manifest v4 + source bundle. В manifest есть
одна запись на Article и отдельная запись на observation; private тексты доступны
по Article ID в bundle и в исходном snapshot. `source_evidence_ref` использует
source fingerprint с обычными JSON spaces, weekly cache keys — compact JSON;
file SHA256 относится к bytes целого файла. Не смешивать эти три вида hashes.

## Учёт дат и пригодности

UTC W0 `[2026-10-05, 2026-10-12)`, W1 `[2026-09-28, 2026-10-05)`;
H `[2026-09-07, 2026-10-05)` включает W1 и три более ранние недели.
Окна ниже не пересекаются; конец исключён.

| Окно | Всего с доказуемой неделей | Timestamp с исходным доказательством | Date-only с однозначной неделей | Проверенный исходный текст | Совместимый accepted admission | Пригодные кандидаты | Остальной unresolved input |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W0, Oct 5–11 | 266 | 248 | 18 | 266 | 29 | 29 | 237 |
| W1, Sep 28–Oct 4 | 158 | 133 | 25 | 158 | 21 | 21 | 137 |
| H2, Sep 21–27 | 95 | 64 | 31 | 95 | 16 | 16 | 79 |
| H3, Sep 14–20 | 199 | 176 | 23 | 199 | 24 | 24 | 175 |
| H4, Sep 7–13 | 214 | 188 | 26 | 214 | 24 | 24 | 190 |
| **35 дней** | **932** | **809** | **123** | **932** | **114** | **114** | **818** |

H отдельно: 666 датированных кандидатов, 85 с совместимым admission.
Это Article counts до weekly classification/event deduplication, не метрики событий
или доли внимания. Все weekly assignments ещё требуют подходящего semantic input
и успешного совместимого cache либо модельной обработки на следующем этапе.

«Проверенный текст» означает целостный сохранённый source-page extraction с
сохранённым quality verdict, либо исходный body, совпадающий с доказательством
admission. Для 932 записей это 922 page extractions и 10 admitted source bodies.
Summary и длина текста не использовались как самостоятельное доказательство.
Сохранённый extraction/model verdict не является независимой ручной проверкой
истинности статьи. Corpus в контекст Codex не выводился.

Из 818 unresolved датированных записей: **630** без совместимого admission,
**187** с сохранённым negative assessment без окончательного допуска и
**1** с явным admission disagreement. Они остаются в учёте и не могут молча
исчезнуть из отчёта вследствие provider failure. Daily summary/category hold
сам по себе не является причиной исключения из weekly.

Ещё **26 date-only Article** имеют неоднозначную границу недели. У шести есть
accepted admission, у трёх сохранённый negative assessment, остальные 17 unresolved.
Они удержаны отдельно. Для календарной даты manifest хранит возможный UTC interval
при неизвестном offset в диапазоне `[-12, +14]` часов; synthetic midnight не создан.
Предположение о диапазоне явно записано в каждом интервале.

Из 114 пригодных кандидатов **14 date-only** требуют calendar-precision adapter:
W0 4, W1 2, H2 3, H3 3, H4 2. Их неделя определима, но UTC publication day
не определён точно. Текущий `Observation` требует datetime: напрямую передавать
в него выдуманный midnight нельзя. Нужен честный учёт неопределённости для
event matching/day-support либо сохранение этих материалов только в фактах.

### Unassigned pool и проверка общей суммы

| Класс без доказуемого назначения неделе | Article |
| --- | ---: |
| Legacy/unverified | 691 |
| Unknown | 829 |
| Publication conflict | 92 |
| Confirmed upstream, но потерян raw literal/precision нормализованного времени | 738 |
| **Unassigned** | **2 350** |

В unassigned есть 991 verified source texts и 367 совместимых accepted admission,
но это не доказывает дату. Остальные 1 359 texts unresolved. Неизвестные записи
могут относиться как к выбранным 35 дням, так и к остальной истории.
Ни одна не назначена неделе по `discovered_at`.

Из 822 confirmed upstream normalized timestamps по всей БД у **84** удалось
восстановить raw precision по существующим доказательствам; **46** из них относятся
к выбранным неделям. Остальные **738** оставлены unassigned. Новый fetch не делался,
новых публикационных дат для unknown/legacy cache не дал. Article не переписывались.

Итог: **932 + 26 boundary ambiguous + 2 350 unassigned + 2 685 доказанно вне
выбранных недель = 5 993 Article**. Legacy/unknown/conflict нельзя честно
разнести по W0/W1/H; они показаны отдельным pool. В manifest сохранены nominal
старые окна только для диагностики расхождений, они не являются отбором.

## Article / weekly observation: подтверждённые дефекты

Snapshot содержит 3 684 observations, 7 782 admission records, 164 Source,
152 source versions и 411 coverage attempts. Все Article и observations учтены.
Точные IDs лежат в `manifest.groups`, а причины — в `records`/`observations`.
Часть групп пересекается; складывать их как независимые исключения нельзя.

| Группа | Число | Нужный результат этапа 2 |
| --- | ---: | --- |
| `runtime_wrong_legacy_confirmed` | 767 Article | Не назначать legacy автоматически из-за отсутствия observation; проверить сохранённое доказательство Article |
| `runtime_wrong_legacy_confirmed_raw_verified` | 759 из них | Сохранить доказанную принадлежность окну и precision; остальные восемь требуют отдельного доказательства |
| `manifest_window_without_observation` | 878 Article | Читать полный текущий Article input, включая week-safe calendar dates |
| `stale_date_observations` | 70 observations во всей БД | Article и его актуальная date evidence имеют приоритет |
| `stale_date_in_runtime_window` | 54 observations | Все 54 относятся к Article с текущим `conflict`; старый observation timestamp не должен вернуть их в неделю |
| `stale_text_observations` | 115 observations во всей БД | Старые title/summary/content не подменяют текущий source input |
| `runtime_deleted_rejects` | 85 observations | Не восстанавливать 85 удалённых Article из исторического observation payload |
| `runtime_orphan_rejects` | 161 observations, включая 85 выше | Orphan с reject evidence не допускается |
| `runtime_orphan_unresolved` | 6 observations | Нет текущего Article/admission — явное исключение, без silent resurrection |
| `runtime_current_window_unassigned` | 473 observations | Связанный Article не имеет доказанного текущего окна; это не 473 доказанно «вне окна» |

Deletion evidence: в сохранённом apply manifest 1 467 удалённых Article;
с ними связаны 103 observations во всей БД, 85 попадают в runtime freeze.
Tombstones и ledger keys перенесены в итоговый manifest, исходный hash apply
manifest сохранён в source bundle. Оставшиеся rejected orphans могут быть
наблюдениями никогда не принятых кандидатов, а не удалёнными Article.

Runtime freeze сейчас содержит 1 787 rows: 1 097 fallback rows автоматически
названы legacy; ещё 236 недатированных observations исключены. Safety cap
не сработал. Эти числа не являются корректным входом будущего отчёта.

Уже исправленные Article `95681` и `95682` сохраняют подтверждённые даты
2026-07-01 и 2026-06-29, соответственно. Они вне W0/W1/H и без weekly observations;
их не надо возвращать в октябрь. Доказательства сохранены также в snapshot
из existing date-correction manifest. Это конкретная регрессия для этапа 2.

## Coverage и пределы подтверждения трендов

| Неделя | DB ledger attempts / дни | Log source receipts | Из них `early_stop_hit=true` | Дни log receipts |
| --- | --- | ---: | ---: | --- |
| W0 | 304 / только Oct 10 | 816 | 202 | Oct 5–10; Oct 11 отсутствует |
| W1 | 0 | 902 | 140 | Все семь дней |
| H2 | 0 | 703 | 106 | Все семь дней |
| H3 | 0 | 715 | 191 | Все семь дней |
| H4 | 0 | 725 | 237 | Все семь дней |

Всего сохранены 3 861 source receipts и 20 fetch-run receipts. Копии могут
пересекаться между auto-update и recovery logs; это свидетельства, не автоматически
дедуплицированный coverage ledger. В этих source receipts `errors=0`, но это
не означает отсутствия незафиксированных failed attempts.

Оставшиеся 107 DB attempts относятся к Oct 12 и не входят в report window.
Все 152 версии sources впервые зарегистрированы Oct 10. `Source.created_at`
может доказать наличие источника раньше, но не историю его интервала,
configuration/ownership и expected attempts. Старые logs идентифицируют sources
по source key, DB ledger — по integer ID; нужен явный проверенный mapping.

**Ни одного publisher group, здорового в обоих сравниваемых окнах по действующим
gates, не доказано.** Для W0 отсутствует Oct 11 receipt и большая часть полного
ledger; H/W1 не имеют versioned expected-attempt evidence. Известную truncation
нельзя принимать как полный сбор. Логи сохраняют положительные наблюдения,
но не доказывают нулевой topic count при отсутствии публикаций.

Для этого report date подтверждённые Up/Down требуют отсутствующего сопоставимого
coverage; New дополнительно не имеет доказанной полной H. Нельзя исправить это
понижением gates или массовым refetch текущих feed pages. Исторические пробелы
должны остаться `coverage_unknown`/`insufficient_history`; факты и темы на
проверенном входе всё равно можно подготовить с явными `insufficient_evidence`.

## Совместимый старый cache

Найден `/opt/ai-news/data/weekly-history/pilot-20261004-budget2/preview.sqlite`.
Его read-only export сохранён в snapshot вместе со старым manifest.
В нём 5 031 decisions: 847 assignment, 3 844 JEV, 332 ambiguity и восемь narrative;
4 184 usage/call records сохранены для аудита прошлых попыток. Это расходы прежнего
pilot, они не были понесены заново на этапе 1.

Model/prompt/token caps, taxonomy и полные topic definitions совпадают с runtime.
Но исходные тексты после cleanup/extraction изменились, а старый frozen pilot
не является актуальным corpus.

Найдены **154 успешных assignment keys с условной совместимостью** на текущем
stored Article tuple: W1 93, H2 53, W0 3, H3 4, H4 1. Точные keys, text hashes
и ограничения находятся в `cache_reuse.conditional_assignments`.
В этих завершённых decisions 110 положительных topic assignments и 44
отрицательных relevance results; последние не являются назначенными AI topics.
Из них **ноль** уже совместимы с выбранным проверенным source input и admission.
Поэтому готового безусловного reuse сейчас не заявляется.

Этап 2 может переиспользовать такой assignment только после подтверждения, что
обрабатывается ровно тот же очищенный/обрезанный текст, task, model, prompt,
taxonomy и caps. Нельзя переносить результат с старой summary на новый полный
page text. Не импортировать `classified:<id>` progress вместе с прежними датами,
eligibility или event IDs. Source admission cache с другой taxonomy не является
готовой weekly topic assignment. Старые narratives привязаны к другим метрикам.

## Конкретные требования к этапу 2

1. В [weekly storage](../src/app/storage/weekly.py) устранить приоритет stale
   observation над актуальными Article/date/admission evidence. Сохранить исходные
   observations для provenance, связать exact canonical/source identity;
   отсеять orphan/deleted rejects без восстановления production rows.
2. Использовать весь frozen scope, отдельный unassigned pool и raw date precision.
   Не превращать 738 upstream-normalized дат в проверенные UTC instants одним
   флагом. Поддержать 26 ambiguous boundaries и 14 пригодных calendar inputs,
   сохранив неопределённость UTC day/support. Проверить исправленные июнь/июль даты.
3. Убрать [worker](../src/app/core/weekly_worker.py) правило «нет observation →
   legacy → eligible=false» для доказанного Article input. Mandatory admission
   остаётся; 818 спорных датированных inputs требуют совместимого source admission
   или явного unresolved состояния. Daily hold/category/Comparison не заменяет
   weekly admission или topic taxonomy.
4. Проверить [calculator](../src/app/core/weekly_analytics.py): сейчас `_metrics`
   и evidence selection ограничены comparable cohort. При пустом cohort они
   обнуляют counts/evidence, поэтому нужно сохранить наблюдаемые факты/источники
   отдельно от недоступных normalized trend metrics. Не выдавать observed raw
   counts за publisher-balanced share и не менять thresholds ради карточек.
5. Подготовить безопасный import успешных decision keys и durable budget/resume
   для изолированного runner. Совместимость по полному ключу проверять до reuse;
   provenance/dates не импортировать из старого pilot. Отдельный frozen input
   fingerprint и новая ревизия отчёта, без повторной оплаты при resume.
6. Проверить регрессии по private IDs групп и synthetic fixtures: stale conflict
   dates, 85 deleted rejects, recovered raw evidence, unknown/normalized dates,
   calendar boundaries, полный 35-day scope, exact-key cache reuse, provider
   failures без исчезновения unresolved denominator, факты при unknown coverage.
   После code changes — полный dev-quality-gate с изолированными БД.
7. Зафиксировать branch/commit/PR и точную команду этапа 3, бюджет/paths/resume и
   штатный `WeeklyStore.publish()` для готовой ревизии без нового model replay.
   Production publication/deploy/scheduler относятся к этапу 4.

Этапу 2 не требуется добиваться нулевого hold во всей БД или полного восстановления
старой истории. Достаточно исправить подтверждённую интеграцию, сохранить честные
coverage limitations и подготовить расчёт доступных частей English report.

## Что опубликовано и как проверен этап

Target `2026-10-11` сейчас существует как legacy stored report ID **215**, созданный
`2026-10-12 01:19:25.351610 UTC`, dates Oct 5–11. Сохранено пять New, ноль Up,
пять Down. Это старые section labels, не проверенные v2 trend conclusions.
V2 target snapshot/publication отсутствует. Исходные report/items сохранены в
`published-target.json`; API GET ради проверки не вызывался, так как handler
вызывает `create_all()` и этап ограничен read-only DB operations.

Проверены hashes immutable snapshot/source bundle/published target, полный учёт
5 993 Article и 3 684 observations, целостность 5 036 caches по evidence/response/
body/HTML/text hashes, исключение tombstones, согласованность counts и private
permissions. Для итогового manifest есть отдельный verification receipt.

**Стоимость этапа 1: $0; JEV/DeepSeek calls 0; дополнительных source fetches 0.**
Содержательные спорные случаи остались явными; новый paid прогон для их решения
не выполнялся. Полные lint/pytest не запускались: application code не менялся,
commit/push не выполнялись; это соответствует правилам read-only этапа.
Semantic precision на всём корпусе данным этапом не сертифицирована.

## Следующая сессия

Открыть [сохранённый промпт этапа 2](prompt-weekly-stage-2-pipeline-2026-10-12.md),
проверить hashes из `handoff-receipt.json` и использовать **manifest v4**.
Выполнить только этап 2; новый export/paid pilot вместо готового snapshot не нужен.
Команда задания следующей сессии: выполнить
`docs/prompt-weekly-stage-2-pipeline-2026-10-12.md`.

Предпочтение пользователя сохранено также в private handoff: каждый новый prompt
для другой сессии сначала сохраняется в `docs/prompt-<task>-<YYYY-MM-DD>.md`;
выдаётся ссылка на файл, предыдущие prompts не перезаписываются.
