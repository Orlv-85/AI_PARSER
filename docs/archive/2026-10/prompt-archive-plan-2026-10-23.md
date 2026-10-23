# Prompt: planner for the full-text article archive (2026-10-23)

You are the **planner** for `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. You write the spec only;
a different session implements it. Read `AGENTS.md` first and follow it. The owner writes Russian
and takes part minimally: decide design questions yourself and report them (AGENTS.md "Owner And
Questions"); only product questions (what readers see) and money questions (paid calls, budgets)
go to the owner, as one-line yes/no questions with a recommendation.

## Goal

Backlog B3, details in `docs/backlog/article-archive-todo.json` (read it fully). Owner goal: keep
the full clean text of every collected AI article permanently, because source pages disappear;
raw material first, interpretation later. Owner decision 2026-10-23: start this before weekly
analytics. A0 (off-site backups) is done.

Scope of this spec: **A1** (where and how to store) and **A3** (capture every day going forward).
**A2** (backfill) only as a short "next spec" section with an estimate; A4-A7 stay in the backlog,
except where A1 must leave room for them.

## Read first (code is the truth, check every claim of the backlog file against it)

- `src/app/core/ingestion/pipeline.md` and `src/app/core/daily/enrichment.md` (code docs: current
  behavior), `src/app/core/daily/signals.md` (how `signal_mentions` survives retention: no FK).
- `src/app/storage/article_evidence_cache.py` (`PageCache`, `SourcePageDownloader`), the RSS full-text
  extraction (`AINEWS_RSS_EXTRACT_FULL_TEXT=1` in `scripts/run_daily_fetch_job.sh`), the article
  model in `src/app/storage/models_sql.py`, `ArticleRepo.prune_older_than` and the non-news
  cleanup (both delete article text).
- `scripts/run_daily_fetch_job.sh`, `scripts/run_daily_digest_job.sh`, `scripts/install_daily_timers.sh`
  (host lock, 4 h budget, fetch 01:00 UTC, digest 02:00 UTC, catch-up after fetch).

## Measure on prod (read-only; `ssh ai-news`, see `docs/deploy.md`; no writes, no restarts)

Refresh the 2026-10-18 facts of the backlog file: articles total and with full text (>= 300
chars) per month and per source (top failing sources), average text size, DB and articles table
size, free disk, size of `data/daily-enrichment/source-cache/`. Known case: openai.com answers 403
to the server, so its articles have title + one line only; list other sources like it. Put the
numbers in the spec with the query you used.

## Write (format of `.specify/templates/`)

`specs/016-article-archive/spec.md`, `plan.md`, `tasks.md`:
- data model (table or files, key, fields, versions of re-extracted text, duplicates across
  sources), migration, retention (archive untouched by prune and cleanup; explicit operator purge
  only), access (never exposed by public APIs or pages), size budget;
- daily capture: where in the nightly flow, under the host lock and inside the budget, never
  blocking or failing fetch, digest or signals; reuse of the existing downloader and cache;
  politeness (per-domain limits, robots.txt, user agent, timeouts); coverage metrics in the job
  log; how a failed capture is retried and when it gives up;
- the code doc the implementer must create next to the main module (AGENTS.md "Feature Docs Next
  To Code") and the tests per rule;
- tasks small enough for one PR each, in order, each with its checks.

## Deliver

- One docs PR from a worktree off `origin/master` (branch `docs/spec-016-article-archive-20261023`),
  spec files only, gate not run (docs only, say so in the PR body). Do not merge.
- Save your report as `specs/016-article-archive/records/report-plan-2026-10-23.md` in the same PR:
  measured numbers, every design decision (found with source / decided by you, dated), open
  owner questions (product or money only) as yes/no with a recommendation, risks.
- Reply with the PR link and the owner questions.
