# Prompt: spec 016 phase 3 - downloads with retries (2026-10-23)

You implement **phase 3 of spec 016** (tasks T008-T009) in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`.
Phases 1-2 and `archive import-db` are merged and deployed (v0.1.123). Prod archive after the seed:
7000 documents, 2959 archived, 4041 pending. The coordinator is session `ai-parser-d4`; report to it
by SendMessage when done. Do not ask the owner design questions (AGENTS.md "Owner And Questions").

## Read first

1. `AGENTS.md`.
2. `specs/016-article-archive/tasks.md` (Phase 3), `plan.md` "Capture steps" (steps 3-7), the
   download / retry / cache sections, "Constants", tests table.
3. `src/app/core/archive/capture.md`, `capture.py`, `src/app/storage/archive.py`.
4. The shared downloader and caches: `SourcePageDownloader`, `PageCache` and the daily-publish
   cache (find them with grep; `tests/unit/test_article_evidence_cache.py`,
   `tests/unit/test_daily_enrichment.py` show how they are used).

## Rules fixed by the coordinator

- Due selection uses the same `first_seen_at` window as coverage (phase 2 decision), so coverage and
  the due set agree; `--all` widens it to every pending document (still capped per run and per host).
- The daily-publish cache is read only, never written or cleared by the capture.
- A retry deletes only the archive cache entry of that URL (`data/archive/source-cache`).
- Outages (network down, DNS failure for every host, timeouts across all hosts) do not count as
  attempts; plan.md defines the rule, follow it.
- Same user agent as the fetcher (`DEFAULT_USER_AGENT`); changing it is out of scope (backlog UA).
- No paid calls, no LLM. `--no-download` keeps today's behavior exactly (no request).
- Summary gets the FR-011 download fields left out in phase 2.

## Steps

1. Worktree: `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER fetch` then
   `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER worktree add ../AI_PARSER-wt-016-p3 -b feat/016-archive-downloads-20261023 origin/master`.
   Remove the import worktree. Checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/<tool>`.
2. Code doc first (`capture.md`): Behavior rules for due selection, cache reuse, downloads, caps
   and time limit, retries, outage, raw page cleanup, each with `Tests:`; Decisions; Code map.
3. T008 in `capture.py` (and `ArchiveRepo` for due / record_result), migration only if plan.md
   needs a column that phase 1 did not create (it should not).
4. T009 tests, names exactly as in tasks.md, all with `httpx.MockTransport`, no network; extend
   `test_capture_summary_reports_coverage`.
5. Checks: scoped tests; `tests/unit/test_article_evidence_cache.py` and
   `tests/unit/test_daily_enrichment.py` unchanged and green; full gate:
   `make lint PYTHON=../AI_PARSER/venv1/bin/python`, `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest`,
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/python scripts/check_code_docs.py`.
6. One local real run on a copy of the local SQLite DB with a small cap
   (`archive capture --max-seconds 120`, caps as in the constants): report the summary JSON and
   how many hosts answered 403/429. Never on the main folder's DB file.
7. Commit `feat(archive): download pending pages with retries (016 phase 3)` with your harness's
   Co-Authored-By line; push; `gh pr create --base master --title "feat(archive): download pending pages with retries (016 phase 3)" --body "<summary, checks, local run JSON, decisions, open questions>"`.
   Do not merge, do not tag, no prod access.

## Out of scope

Nightly job and timers (phase 4), admin stats, user agent change, `scripts/db_maintenance.sh`.

## Report to the coordinator (SendMessage to `ai-parser-d4`)

PR link and head SHA; files changed; tests added; full gate summary; local run JSON; decisions not
fixed by the spec or this prompt, one line each; doubts.
