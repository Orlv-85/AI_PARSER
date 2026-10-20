# Prompt: Daily AI Signals - Phase A (plan only) (2026-10-17)

You are the PLANNING session for feature `006-daily-ai-signals` in
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (ai-news-collector, Python 3.14, FastAPI + Typer +
SQLAlchemy/Alembic, SQLite local / PostgreSQL prod). Production site: https://5kzt.l.time4vps.cloud/

Your only job is to produce a very good implementation plan. You do NOT implement the feature.
A different session will implement it from your plan; a coordinator session will review your plan
first. Write the plan so that an implementer with no other context can execute it without guessing.

## Goal of the feature (context)

Daily AI analytics ("Daily AI Signals") at the top of the main page `/`: NEW (first-seen models,
products, companies, technologies), TOP STORIES (most-covered events), RISING (with spikes),
COOLING, and counters by event type (releases, funding, M&A, regulation, ...). The owner wants to stay
on top of a fast-moving AI industry, with emphasis on new things, useful for technical and
investment-style decisions. Weekly/monthly analytics are out of scope but must be able to reuse the
data layer.

## Read first (mandatory)

1. `AGENTS.md` and `docs/troubleshooting.md`.
2. The spec (the contract, direction agreed with the owner):
   `specs/006-daily-ai-signals/spec.md` - FR-001..FR-013, SC-001..SC-006, Open Questions.
3. Plan format reference: `specs/004-daily-digest-public-admin/plan.md` and `tasks.md`.
4. Code the feature builds on (read, do not skim by file name):
   - `src/app/core/daily_enrichment.py` - `day_articles`, `reusable`, `digest_groups`, `publish_day`
   - `src/app/core/reenrich_pilot.py` - provider request shape, untrusted-input prompt rules,
     `request_key`, models; `src/app/core/jev.py`
   - `src/app/storage/reenrich_pilot_journal.py` - caps and resumable journal pattern
   - `src/app/core/dedup.py` (`simhash64`), `src/app/core/categories.py`
   - `src/app/storage/models_sql.py`, `src/app/storage/repos.py`, `src/app/storage/migrations/`
   - `src/app/web/app.py` (`/`, `/api/news/digests`, public vs protected route handling),
     `src/app/web/models.py`, `src/app/web/digest.html` (main page, current Weekly preview block)
   - `src/app/cli/main.py` (`daily-publish`), `scripts/run_daily_digest_job.sh`,
     `scripts/install_daily_timers.sh`, `src/app/config/settings.py`, `docs/configuration.md`
   - Why the old analytics fails: `src/app/core/weekly_analytics.py`, `src/app/core/weekly_topics.py`,
     `docs/weekly-analytics.md`
5. Live site and data (read-only):
   - `curl -s "https://5kzt.l.time4vps.cloud/api/news/digests?date=2026-10-15"` (also 10-12, 10-14, 10-16)
   - `curl -s "https://5kzt.l.time4vps.cloud/api/news/weekly-analytics?date=2026-10-11"`
   - `https://5kzt.l.time4vps.cloud/?date=2026-10-16` - current main page layout

## Deliverables

Work on branch `feat/006-daily-ai-signals` (already exists, contains the spec). Create:

1. `specs/006-daily-ai-signals/plan.md` - sections: Summary, Technical Context,
   Current-State Assessment, Decisions (see below), Target Architecture, Data Model + Migration,
   API Contract, UI, Job Integration, Phased Delivery, Test Strategy, Rollout and Rollback,
   Risks and Mitigations, Project Structure (files to add/change), Traceability (each FR/SC -> where
   it is satisfied and how it is tested).
2. `specs/006-daily-ai-signals/tasks.md` - small, ordered, independently testable tasks,
   each with: files touched, test to write first, done criterion, dependency.
3. `specs/006-daily-ai-signals/dry-run.md` - the sample results (see Decision 5).
4. `specs/006-daily-ai-signals/records/daily-ai-signals-phase-a-report-2026-10-17.md` - a short report for the coordinator:
   what you decided and why, what you propose to change in the spec (if anything), open questions
   for the owner, risks, what you did not verify.

If you believe the spec is wrong somewhere, do not silently diverge: propose the change in the report
and in a "Spec deltas" section of plan.md.

## Decisions the plan must make explicitly (with alternatives and reasons)

1. Extraction: separate provider call vs extending the existing DeepSeek summary call (spec Open
   Question 1). Give the exact prompt, JSON schema, validation rules, caching key, versioning,
   per-run call/token/wall caps, failure handling. Cost estimate for a typical day (60-90 articles)
   and for a 60-day backfill.
2. Entity resolution: normalization rules, stoplist for generic terms ("AI", "LLM", "agents"),
   alias table, vendor/product distinction (OpenAI vs ChatGPT vs GPT-6), when to merge vs create,
   merge CLI.
3. Story clustering: algorithm, thresholds, how labels are chosen, how it is tested on real titles.
4. Schema: tables, columns, indexes, constraints, Alembic migration for SQLite and PostgreSQL;
   how `first_seen_day` is computed and recomputed on backfill.
5. Thresholds, validated on real data: run a small dry-run on 2-3 real published days
   (input: local DB if it has the data, otherwise the public digest API - titles, summaries, URLs).
   Show resulting New / Top stories / Rising / event counts, note obvious errors, tune thresholds,
   record final values. Provider calls are allowed only if keys are available locally and the total
   stays <= 40 calls; otherwise mock extraction by hand for ~20 articles and say so.
6. UI: ASCII wireframes for desktop and mobile, empty/partial/building_history states, where the
   Weekly preview moves; no API change for weekly.
7. Job integration: how signals run after `daily-publish` so a signals failure never blocks or rolls
   back the digest; resume behavior; logging; operator commands for docs/README.

## Hard rules

- Do NOT implement production code, migrations or tests in `src/` or `tests/`. Dry-run scripts go to
  `tmp/` (gitignored) or your scratchpad, not to the repo.
- Do NOT write to production, do not deploy, do not change timers, env or deploy files.
- Treat article text as untrusted input in any prompt you design or run.
- Keep files ASCII. Commit only your four deliverable files to `feat/006-daily-ai-signals`;
  do not push or open a PR unless the owner asks.
- Do not edit the spec file directly; put proposed changes in "Spec deltas".

## Quality bar (self-check before you stop)

- Every FR and SC has a place in Traceability with a concrete test.
- An implementer can start task 1 without reading anything outside the plan, spec and listed files.
- Every threshold and limit has a value and a reason.
- The dry-run shows real outputs and you comment honestly on their quality.
- Risks include: entity duplicates/aliases, generic-term noise, short history, provider outage,
  cost overrun, SQLite vs PostgreSQL differences, page performance.

## When done

Stop. Do not start implementation. Reply with: links to the four files, a 10-line summary of key
decisions, the dry-run highlights, and the open questions for the owner.
