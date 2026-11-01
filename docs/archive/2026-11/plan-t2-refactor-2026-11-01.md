# Plan: backlog T2, refactoring of complex, duplicated and dead code (2026-11-01)

Measured on `origin/master` at 615f41e (merge of PR #168) in a temporary worktree, now removed. No
code changed, no commit, no PR. Source: 20,788 lines in `src` (Python), plus 3 JS files in
`src/app/web/static`.

## 1. Measurements

### Tools and commands

| Tool | Version | Source |
| --- | --- | --- |
| crapper | 0.1.0 | `~/tools/unclebob/crapper` (commit 6fd92c4) |
| dryer | 0.1.0 | `~/tools/unclebob/dryer` |
| mutator | 0.1.0 | `~/tools/unclebob/mutator` |
| vulture | 2.16 | separate venv in the scratchpad, not `venv1` |
| coverage.py | 7.16.2 | `venv1`, unchanged |

```
# coverage: crapper's own run was not used; pytest under coverage, then lcov
PYTHONPATH=src venv1/bin/python -m coverage run -m pytest -o addopts="" -q -p no:cacheprovider
venv1/bin/python -m coverage lcov -o target/coverage/python/lcov.info
crapper --use-existing-coverage src
dryer --threshold 0.8 src
mutator --use-existing-coverage --max-workers 2 \
  --test-command "venv1/bin/python -m pytest -o addopts= -q -p no:cacheprovider tests/unit/test_world_filter.py" \
  src/app/core/world/filter.py
vulture src --min-confidence 60        # hint only
```

Suite for the coverage run: 1552 passed, 1 skipped, 141 s; total coverage 96% (branch on). Crapper
scores by line coverage of each function from the lcov file.

### CRAP (crapper with coverage)

909 functions scored: 858 Python, 51 JavaScript (crapper reads `src/app/web/static` as TypeScript;
the repo has no JS tests, so every JS function is at 0%).

| Group | CRAP >= 30 | CRAP 10 to 30 | CC >= 10 |
| --- | --- | --- | --- |
| Python | 4 | 102 | 94 |
| JavaScript | 19 | 15 | 7 |

The owner's "about 100 functions with CC >= 10" matches (94 Python + 7 JS). Of the 94 Python
functions with CC >= 10, 52 are 100% covered, so their CRAP equals CC; the CRAP 10-30 count is mostly
"complex but tested".

Python, CRAP >= 30:

| Function | Module | CC | Cov | CRAP |
| --- | --- | --- | --- | --- |
| `PilotJournal.review_quote_failure` | `storage/provider_journal.py` | 11 | 0% | 132.0 (dead, see 1.4) |
| `source_row` | `core/daily/enrichment.py` | 19 | 35.7% | 114.9 |
| `_screen_candidate` | `core/ingestion/pipeline/screening.py` | 25 | 68.4% | 44.7 |
| `_process_html_links_two_stage` | `core/ingestion/pipeline/html_links.py` | 34 | 91.7% | 34.7 |

Next in CRAP 10-30 (worth a look, all tested 66% to 100%): `fetch_one` 29.4 and `inspect_page` 22.5
(`storage/article_evidence_cache.py`), `_process_fetched_source_items` 29.0 (`pipeline/rss.py`),
`build_sources_router` 29.0, `_build_article_row` 28.0 (`pipeline/rows.py`), `parse_summary` 27.9
(`daily/provider_requests.py`), `_sentence` 27.0 (`daily/signals_brief.py`), `render_signals` 27.0
(`web/signals_view.py`), `run_fetch_cycle` 25.4 (`pipeline/cycle.py`), `extract_date_evidence` 25.2
(`ingest/date_evidence.py`), `create_app` 25.0, `_download_step` 24.0 (`archive/capture.py`),
`_assessment_from_cached` 23.3 (`pipeline/screening.py`), `PilotJournal.call` 22.1, `publish_day` 21.4
and `enrich` 19.3 (`daily/enrichment.py`).

Caveats that change the ranking:

- Crapper charges nested functions to the enclosing function. `build_sources_router`,
  `build_pages_router`, `build_news_router`, `build_period_router`, `create_app` are FastAPI route
  factories: their CC is the sum of many small handlers. They are a measurement artifact, not a
  refactoring target.
- `_sentence`, `_entity`, `render_signals` are 100%-covered rule/lexicon code; CRAP = CC. Low value.
- Pipeline modules: 7 functions with CC >= 10 in `core/ingestion/pipeline`, the largest concentration.
- JavaScript, CRAP >= 30 (all 0% coverage): `loadOnboardingCandidates` 44 (1980),
  `renderSignals` 38 (1482, `js/digest.js`), `loadNews` 23, `validateSettings` 19, `refreshSourceCheck`
  18, and 14 smaller ones. Not actionable without a JS test setup (see section 3).

### Duplicates (dryer)

At the default 0.82 the run gives 12 reports; at 0.8 it gives 17 (8 at >= 0.9, not 9 as in the
backlog note; the code moved since). Grouped:

| Group | Score | Locations | Verdict |
| --- | --- | --- | --- |
| A. Candidate field readers (dict or attribute, required str / optional str / optional int) | 1.0, 0.9, 0.8 | `core/sources/candidates.py:285-292` (`_candidate_value`), `core/sources/onboarding.py:288-295` (`_candidate_int_value`), `storage/source_repo.py:164-176` (`_read_object_value`) and `:232-239` (`_read_int_value`), `storage/source_candidate_repo.py:111-123` (`_read_candidate_value`) and `:262-269` (`_read_optional_value`) | Real: 6 copies of one decision. PR 3 |
| B. `_probability` | 1.0 | `core/jev.py:35-43` vs `core/sources/review.py:138-142`; same check, different error text | Real but `jev.py` is rewritten by spec 018 item 1; leave until it lands |
| C. `set_collection_paused` / `clear_collection_paused` | 0.87 | `storage/admission.py:35-40` vs `:43-48` | Real, tiny. PR 4 |
| D. `private_bytes` / `private_write` | 0.84 | `storage/article_evidence_cache.py:57-65` vs `storage/journal_files.py:26-35`; same 0o600 write-fsync-replace dance | Real. PR 5 |
| E. Alembic `downgrade()` bodies | 1.0 to 0.8 (7 pairs) | `migrations/versions/*` | Not touched: generated and applied history |
| F. `exists_by_canonical_hash` vs `find_by_normalized_url` | 0.82 | `storage/article_repo.py:42-48`, `storage/source_candidate_repo.py:148-152` | False positive: same SQLAlchemy select shape, different tables |

### Mutator (one module)

`core/world/filter.py` with `tests/unit/test_world_filter.py`, 2 workers, 25 s, exit 3 (a survivor):
24 killed, 2 survived, 2 uncovered, 28 sites, score 92.3%. The tests are strong.

- Survived `filter.py:110` `>=` to `>` (`_is_all_caps`): no test with exactly `ALL_CAPS_MIN_LETTERS`
  (8) cased letters.
- Survived `filter.py:173` `False` to `True` in `filter_title` (no-match result): the test checks the
  reason but not `kept is False`.
- Uncovered `filter.py:156` (`load_own_domains`, the `or` fallbacks for an empty file / source
  without url).

Two assertions would close it, but `core/world/` is being rewritten (section 3), so no PR now.

### Dead-code candidates (vulture, then caller check)

Vulture at 60% gave 287 lines; 250 are false positives of known kinds: Alembic `revision`,
`upgrade`, `downgrade`; FastAPI route handlers and pydantic fields in `web/models.py`; Typer commands
in `cli/main.py`; pydantic validators; SQLAlchemy type hooks. The 16 plain functions, methods and
classes outside those were checked against `src`, `tests`, `scripts`, `deploy`, `automation`,
`Makefile`, docs, templates and static JS. Also checked: modules nothing imports (none).

| Candidate | Callers found | Verdict |
| --- | --- | --- |
| `core/ingestion/reject_policy.py:20` `article_evidence_hash` | none anywhere | Dead |
| `PilotJournal.review_quote_failure` | none (only a spec-010 prompt names it); 0% covered | Dead |
| `PilotJournal.has_reviewed_response` | none (only a spec-006 review mentions it) | Dead |
| `PilotJournal.has_response` | tests only (`test_provider_requests.py:216,218`); spec 006 review says it ignores the injected key function | Dead in production, test-only |
| `PilotJournal.review_truncated_summaries` | tests only; one-off pilot recovery of billed truncations | Dead in production, test-only |
| `PilotJournal.restore_valid_summary` | tests only; same | Dead in production, test-only |
| `core/ingestion/admission.py:13` `ADMISSION_CHOICES` | none | Dead constant |
| `core/periodic/period_run.py` `BACKFILL_MAX` | none (the doc does not name it) | Dead constant |
| `core/periodic/period_model.py:16` `STATUSES`, `storage/daily_signals_ledger.py:28` `FAILURE_STATES` | defined only | Likely dead constants; confirm in the PR |
| `web/period_view.py:51-56` `NOT_YET`, `UNREADABLE`, `FIRST_WEEK`, `LOW_COVERAGE`, `PARTIAL` | defined only (`NOT_FOR_WEEK` is used) | Likely dead; confirm templates in the PR |
| `period_run.py` `first_week`, `latest_completed_week`, `first_month`, `latest_completed_month`, `target_weeks`, `target_months` | tests and `signals_period.md` only; thin wrappers over `first_period`, `latest_completed`, `target_periods` | Dead in production, test-only |
| `core/world/gdelt.py:30` `FILES_PER_KIND` | test and module itself | Keep (not flagged as dead; used in the module) |
| `web/auth.py:46` `hash_password` | tests only, but `AINEWS_AUTH_PASSWORD_HASH` needs a hash and the repo has no other generator | Keep: operator tool |
| `config/sources.py` `bootstrap_sources_into_db` | `scripts/sources_onboarding_helper.py:624` | Live |
| `core/sources/onboarding.py` `export_approved_sources_yaml` | `scripts/sources_onboarding_helper.py:646` | Live |
| `storage/world.py` `candidates_in_state`, `transition` | `world.md`, tests, the world job | Live (and rewritten by 018) |
| vulture on `core/world_collect.py` (`pruned_*`), `pipeline/models.py` counters, `storage/archive.py` `last_issue`, `daily/signals_model.py` `chip_hard_events` | dataclass fields written but read through `asdict` / JSON | Not dead without a per-field check; not in this plan |

## 2. PR list, in order

Rules for all PRs: one PR per module or per duplicate group; the doc first if a code doc covers the
file (AGENTS.md "Feature Docs Next To Code"); a different session reviews; full gate
(`make lint`, `./venv1/bin/pytest`) before commit; each deletion listed in the PR with its reason
(ub-mode). Behavior-preserving only: no CLI, API, schema or stored-data change.

| # | PR | Files | What changes | Tests pinning it first | Risk | Code doc | Production-sensitive |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Delete zero-reference dead code | `core/ingestion/reject_policy.py`, `storage/provider_journal.py`, `core/ingestion/admission.py`, `core/periodic/period_run.py`, `core/periodic/period_model.py`, `storage/daily_signals_ledger.py`, `web/period_view.py` | Remove `article_evidence_hash`, `PilotJournal.review_quote_failure`, `has_reviewed_response`, `ADMISSION_CHOICES`, `BACKFILL_MAX`, and (after confirming no reader) `STATUSES`, `FAILURE_STATES`, the five `period_view` constants; drop imports that become unused. Removes the top Python CRAP (132). | None needed (no references). `ruff`, `mypy`, full suite. | low | `pipeline.md` covers `provider_journal.py`; check it names none of these (grep found none). | `provider_journal.py` is the paid-call journal (digest and Jev calls): deleting methods that never run cannot change spend; still flag |
| 2 | Delete production-dead, test-only code | `storage/provider_journal.py`, `tests/unit/test_provider_requests.py`, `core/periodic/period_run.py`, `core/periodic/signals_period.md`, tests of period | Remove `has_response`, `review_truncated_summaries`, `restore_valid_summary` with their test blocks; replace the six `period_run` wrappers by `first_period`/`latest_completed`/`target_periods(kind)` calls in the tests and fix `signals_period.md` lines 158, 162, 381 | The tests that use them are rewritten to call the generic functions (same assertions) in the same PR | low | `signals_period.md` and `pipeline.md`: edit doc first | Paid-call journal, same note as PR 1. Do not start before 018 item 1 is merged or confirmed not to use these methods (it uses `PilotJournal`) |
| 3 | One candidate-field reader | New small helper next to `core/sources/candidates.py`; `candidates.py`, `onboarding.py`, `validation.py`, `storage/source_repo.py`, `storage/source_candidate_repo.py` | Group A: one `read_field(candidate, name, *, default, required)` plus thin `str` / `int` / optional forms; the six copies call it. Check the import direction (storage must not import web; core is already imported by storage in places) before choosing the module | Existing: `test_source_candidate_repo_edges.py:73,76`, `test_source_onboarding_edges.py:240`, `test_source_repo_edges.py`; add a table test of the helper (dict vs object, missing, None, default, int cast, error text `candidate field is required: <name>`) | low | `onboarding.md` covers all of `core/sources/*.py`, `source_candidate_repo.py`; update Code map | Source onboarding is operator-only; `source_repo.py` is also read by ingestion but only these static readers change |
| 4 | Collection pause set/clear | `storage/admission.py` | Group C: one private `_write_pause(session, paused, message)`; keep both public functions | `test_screening_notice.py` (uses both); add an assertion on `updated_at` set and `flush` | low | `pipeline.md` (covers `storage/admission.py`) | Ingestion pause gate: flag |
| 5 | One private-file writer | `storage/journal_files.py`, `storage/article_evidence_cache.py` | Group D: `private_bytes` and `private_write` share one open(0o600) / fchmod / fsync / replace routine | `test_journal_files.py`; add a test that `private_bytes` creates the file with mode 0o600 and replaces atomically (leaves no `.next`) | low-medium (file permissions, atomic replace) | `archive/capture.md` covers the cache; `enrichment.md` names `private_write` | Used by the daily digest job (`enrichment.py`) and archive job: flag |
| 6 | Characterization tests for `source_row` | `tests/unit/test_daily_enrichment.py` (or new) | Tests only: cover the 64% of `source_row` that no test reaches (CC 19, cov 36%); no source change | New: one case per branch of `source_row` | low | `enrichment.md` | Daily digest: flag |
| 7 | Split `source_row` and `publish_day` | `core/daily/enrichment.py` | Extract the branches into small named helpers; same outputs | PR 6, plus `test_daily_enrichment.py` | medium | `enrichment.md`: Code map | Daily digest, paid calls: flag; do after 018 items 1 to 4 if they edit `enrichment.py` (confirm first) |
| 8 | Characterization tests for screening | `tests/unit/test_semantic_admission_pipeline.py` or new | Tests only: `_screen_candidate` (CC 25, 68%) and `_assessment_from_cached` (CC 15, 67%) | New | low | `pipeline.md` | Ingestion |
| 9 | Split `_screen_candidate`, `_assessment_from_cached` | `core/ingestion/pipeline/screening.py` | Extract decision steps; same outputs | PR 8 + `tests/integration/test_pipeline.py` | medium-high | `pipeline.md` Code map | Ingestion: flag |
| 10 | Split `_process_html_links_two_stage` (CC 34) | `core/ingestion/pipeline/html_links.py` | Extract stages; the function is already 92% covered | Existing pipeline tests and fixtures in `tests/fixtures/html`; add cases for uncovered branches first | high | `pipeline.md` | Ingestion: flag |
| 11 | Split `_process_fetched_source_items` (CC 29), `run_fetch_cycle` (CC 25) | `pipeline/rss.py`, `pipeline/cycle.py` | Same method; one PR each | Existing + `tests/fixtures/rss` | high | `pipeline.md` | Ingestion: flag |
| 12 | Split `_build_article_row` (CC 27) | `pipeline/rows.py` | Same method | Existing | medium-high | `pipeline.md` | Ingestion: flag |
| 13 | Split `SourcePageDownloader.fetch_one` (CC 25), `inspect_page` (CC 21) | `storage/article_evidence_cache.py` | Same method | Existing archive tests (`test_archive_capture.py` and cache tests) | medium | `archive/capture.md` | Archive job |
| 14 | `parse_summary`, `parse_jev` in `provider_requests.py` | `core/daily/provider_requests.py` | Tests for the 25% uncovered branches first, then split | New | medium | `pipeline.md` covers `jev.py` only; check | Paid-call parsing: flag; wait for 018 item 1 (it extends Jev) |
| 15 | Remaining CC 10-15 functions, grouped by module | `daily/signals_*`, `periodic/*`, `ingest/html.py`, `sources/candidates.py` | Only where a function is also below 100% coverage; skip 100%-covered pure rules | Per function | low-medium | per module | Daily signals: flag |

Order logic: PRs 1 to 5 are the cheap, mostly deletion and duplicate work the backlog asked to start
with. PRs 6, 8 are test-only and can run in parallel with them. PRs 9 to 14 (the worst complexity)
come last because they are the riskiest and sit in ingestion and the daily digest; do them in the
order of CRAP (7, 9, 10) and one per session.

## 3. What not to touch

- `src/app/core/world/*`, `src/app/storage/world.py`, `src/app/core/world_collect.py`,
  `scripts/run_daily_world_job.sh`: spec 018 item 5 rewrites them; worktrees for
  `feat/018-world-w3-storage` and `feat/018-world-w4-collect` are active. This includes the
  mutator survivors in `world/filter.py` (revisit after item 5).
- `src/app/core/jev.py` and the `_probability` duplicate (group B): spec 018 item 1 (Jev questions)
  changes Jev. Do the dedupe after it merges.
- `src/app/core/bulletin/world_change*.py`, `src/app/storage/world_change.py`: new 018 code.
- `src/app/web/static/js/digest.js`, `web/pages.md` area, `web/routes/pages.py`, `core/daily/signals_*`
  UI-facing code: 018 item 6 replaces the home page and moves the digest to `/daily`.
- `src/app/storage/migrations/versions/*`: generated, applied history; the duplicate `downgrade()`
  bodies (group E) and vulture noise stay.
- JavaScript in `src/app/web/static/admin/*` and `js/*`: 19 functions with CRAP >= 30 only because
  there are no JS tests. A refactor without tests breaks the rule "pin behavior first"; adding a JS
  test setup is a tooling decision, not part of T2. Backlog item suggestion: separate "JS test
  harness" task.
- FastAPI route factories (`build_*_router`, `create_app`) and 100%-covered rule code (`_sentence`,
  `_entity`, `render_signals`): high CC is structure, not risk.
- `web/auth.py` `hash_password`: tests-only but the only hash generator for a production secret.
- Pydantic model fields, Typer commands, SQLAlchemy hooks flagged by vulture: framework entry points.
- Any change to ingestion thresholds, admission rules, digest wording, paid-call budgets, deploy
  scripts, ports, retention.

## 4. Open questions

No question for the owner (no product or money question: nothing here changes what readers see or
what is paid).

For the planner / reviewer session (not the owner):

- Does spec 018 item 1 or 4 touch `core/daily/enrichment.py` or `PilotJournal` methods? It decides
  whether PRs 2, 7 and 14 go now or after item 4. Not answered by the spec text I read.
- PR 3 helper location: `core/sources/` is the proposal; decide at review if storage importing from
  `core` is acceptable (check existing imports in `storage/`).
- Whether crapper/dryer/mutator run in CI (advisory) is a separate backlog item, not part of T2.
