# Plan: split overloaded modules (2026-10-21)

Status: planned splits complete (2026-10-21). Review it in another session before anyone splits a file. Paths are after
the `core/` regrouping (same PR as this file). Line counts are from that branch.

Step 1 done (2026-10-21): `storage/repos.py` split, branch `refactor/split-storage-repos-20261021`.
Step 2 done (2026-10-21): `core/sources/onboarding.py` split.
Step 3 done (2026-10-21): `web/app.py` split into `web/routes/`, branch
`refactor/split-web-app-20261021`.
pipeline.py split 2026-10-24 (owner decision), guard test `tests/unit/test_monkeypatch_targets.py`.

## Method

Every file in `src/app` over ~550 lines, plus files with several `too-many-*` pylint disables, was
read for its top-level definitions, importers and test monkeypatches. A file is "overloaded" when it
mixes unrelated concerns, not just when it is long. Cost counts: files that import it, quoted
monkeypatch strings (`"app.x.y.NAME"`) and `monkeypatch.setattr(module, "NAME")` calls in tests,
and code-doc changes.

General rules for every split PR:

- One PR per file, moves only (as in the `core/` regrouping): `git mv` for the largest part so
  history follows, no logic edits, same pytest pass count before and after.
- A patched name must stay in the module whose functions look it up. Before moving a function, list
  the names tests patch on the old module and check which of them the function reads; otherwise the
  patch silently stops applying.
- No re-export shims unless the plan says so for a file (a shim hides where a name lives and
  makes monkeypatching ambiguous).

## Summary

| Order | File | Lines | Recommendation |
| --- | --- | --- | --- |
| 1 | `storage/repos.py` | 1605 | split (four repos out; weekly repo waits) |
| 2 | `core/sources/onboarding.py` | 1005 | split in three |
| 3 | `web/app.py` | 1374 | split into routers |
| - | `core/ingestion/pipeline.py` | 1446 | leave |
| - | `core/daily/signals_compute.py` | 799 | split 2026-10-24 (owner decision) |
| - | `storage/daily_signals.py` | 602 | leave |
| - | `web/service.py` | 574 | leave |
| - | `storage/models_sql.py` | 562 | leave |
| - | weekly v2 files | - | deferred, no recommendation |

## 1. `storage/repos.py` (1605 lines) - split

Mixes: six unrelated repositories in one file: `SourceRepo` (registry, fetch state, sources created
from candidates), `ArticleRepo` (article upsert, view/agent/search queries, daily stats),
`WeeklyAnalyticsRepo` (~500 lines: legacy weekly report, title-topic heuristics, v2 hydrate),
`SourceImportBatchRepo` and `SourceCandidateRepo` (source onboarding), `NewsDigestRepo`.
`too-many-lines` and `too-many-branches` disables.

Proposed split:

- `storage/source_repo.py` - `SourceRepo`.
- `storage/article_repo.py` - `ArticleRepo`, `ArticleDailyStats`, `_publication_since/_before`.
- `storage/source_candidate_repo.py` - `SourceImportBatchRepo`, `SourceCandidateRepo` (the
  `TYPE_CHECKING` import of `CandidateOverlapGroup` goes with it).
- `storage/digest_repo.py` - `NewsDigestRepo`.
- `storage/repos.py` keeps `WeeklyAnalyticsRepo` and its dataclasses until the weekly v2 decision
  (see "Weekly v2"); it is not touched beyond removed classes.

Cost: 37 files import `app.storage.repos` (src, tests, scripts); each import line names the classes
it uses, so the change is mechanical. One monkeypatch string
(`"app.storage.repos.SourceCandidateRepo.record_validation_result"` in
`tests/integration/test_source_validation_flow.py`) patches a class attribute, which follows the
class. No code doc covers these files; the pipeline doc Code map names `ArticleRepo`/`SourceRepo`
by class only.

Risk: low. Classes do not call each other except `SourceRepo.create_from_candidate` reading
candidate rows (ORM models, not the repo class).

Recommendation: split first. Clear seams, almost no patch churn, and it makes the onboarding and
web splits smaller to review.

## 2. `core/sources/onboarding.py` (1005 lines) - split in three

Mixes: (a) pure URL work: extracting, normalizing and classifying candidate URLs, batch flags and
overlap grouping (`normalize_candidate_url`, `parse_source_candidates`, `classify_candidate_batch`,
`group_candidate_overlaps` and ~25 private path helpers); (b) network validation of candidates
(`validate_rss_candidate`, `validate_html_candidate`, `run_source_validation(_batch)`,
`_fetch_*_with_ingest`); (c) DB actions: import, review (approve/reject/disable/duplicate/edit),
YAML export.

Proposed split:

- `core/sources/candidates.py` - (a), no DB and no network.
- `core/sources/validation.py` - (b).
- `core/sources/onboarding.py` keeps (c), the dataclasses shared by all three stay here or move to
  `candidates.py` (whichever has no import cycle; decide in the PR).

Cost: 15 importing files; 6 test files import the module object (`from app.core.sources import
onboarding as source_onboarding`) and patch `SourceCandidateRepo` (5x, stays with (c)),
`run_source_validation` (1x, read by `run_source_validation_batch`: both move to
`validation.py`, the patch target changes) and `Fetcher` (1x, moves to `validation.py`). Four
quoted strings: `group_candidate_overlaps` 2x (moves to `candidates.py`; `storage/repos.py` imports
it lazily, so the string must name the module the caller reads from), `classify_candidate_batch`
1x (-> `candidates.py`), `run_source_validation` 1x (-> `validation.py`).
`sources/review.py` imports `normalize_candidate_url` (-> `candidates.py`). No code doc yet; the
split PR is the moment to write `core/sources/onboarding.md` (AGENTS.md: older features get a doc
when next changed).

Risk: low to medium: the patch targets above are the only trap; each is listed.

Recommendation: split second, after `repos.py`.

## 3. `web/app.py` (1374 lines) - split into routers

Mixes: one `create_app` (`too-many-statements`) holding the auth middleware and 39 route closures
for six areas: HTML pages and login/logout; news list/export/links/article; digest and daily
signals; weekly analytics (legacy and v2 reads, freshness); update settings and runs; source
onboarding admin (13 routes). Module-level render/response builders (~320 lines) serve each area.

Proposed split: `web/routes/{pages,news,signals,weekly,updates,sources}.py`, each an `APIRouter`
built by a function that takes what the closures capture today (`settings`, `settings_store`,
`update_service`, `source_intake`, session factory, signer); `create_app` builds the shared
objects, adds the middleware and includes the routers in today's order. Response builders move with
their routes.

Cost: 14 test files import only `create_app` (13) or `app` (1) from `app.web.app`, and no test
patches an `app.web.app` name, so test churn is near zero. No code doc covers it.

Risk: medium: route registration order (a path parameter route registered before a fixed path) and
middleware/auth coverage of every route; both are checked by the existing web tests, plus a test
that compares the sorted route table before and after.

Recommendation: split third. Largest readability gain for web work, but more design (router
factory signature) than the first two; the design question goes to the reviewing session.

## Leave as is

- `core/ingestion/pipeline.py` (1446) - long, but one flow (fetch cycle) with a fresh code doc and
  refactor (PRs #61-62). Tests patch 21 different names on this module 82+ times
  (`fetch_html_article`, `SessionLocal`, `jev_relevance_scorer`, `_collect_fetched_items`, ...,
  plus loops in `test_pipeline_runtime.py`), and each moved function would have to keep reading
  those names from `pipeline`. Cost and silent-patch risk are high for little gain. Revisit when a
  behavior change touches the HTML two-stage path (`_process_html_links_two_stage`, ~170 lines),
  the one block that could become `ingestion/html_links.py` with its fetch functions.
- `core/daily/signals_compute.py` (799) - signals_compute.py split 2026-10-24 (owner decision). Earlier note: one concern (snapshot of one day); half is the
  `_Snapshot` class. Covered by `core/daily/signals.md` and pinned fixtures; splitting would only
  move helpers. The `too-many-instance-attributes` disables are on plain dataclasses.
- `storage/daily_signals.py` (602) - one repository of one feature (`too-many-public-methods`
  on `DailySignalRepo`); cohesive.
- `web/service.py` (574) - two services (`UpdateRunService`, `SourceOnboardingService`, ~190
  lines). Tests patch `app.web.service.get_settings` 8x and other names used by both; a split
  doubles patch targets for a small file. Leave.
- `storage/models_sql.py` (562) - ORM models; one place for the schema is the convention.
- Smaller files with `too-many-*` disables (`ingest/page_filter.py`, `ingest/date_evidence.py`,
  `storage/article_evidence_cache.py`, `storage/legacy_cleanup.py`, `storage/reenrich_apply.py`,
  `mcp/server.py`) carry one long function each, not mixed concerns.

## Weekly v2 (deferred, no recommendation)

Keep-or-delete is decided when weekly work starts; no split is proposed until then. Files:
`core/weekly/frozen.py` (591), `core/weekly/enrichment.py` (457), `core/weekly/analytics.py` (354),
`core/weekly/narrative.py` (183), `core/weekly/worker.py` (139), `core/weekly/input.py` (102),
`core/weekly/audit.py` (85), `core/weekly/topics.py` (81), `storage/weekly.py` (353); v2 parts
inside other files: `WeeklyAnalyticsRepo._hydrate_v2` and the `weekly_v2_enabled` branches in
`storage/repos.py`, `_record_weekly_observation` / `_publish_weekly_analytics_if_due` in
`core/ingestion/pipeline.py`, weekly commands in `cli/main.py`, weekly routes in `web/app.py`.
