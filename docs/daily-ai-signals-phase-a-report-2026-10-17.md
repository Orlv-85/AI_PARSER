# Daily AI Signals - Phase A Report (2026-10-17)

For: coordinator session. Scope: planning only; no production code, migrations or tests were written.

Deliverables:

- Plan: `.specify/specs/006-daily-ai-signals/plan.md`
- Tasks: `.specify/specs/006-daily-ai-signals/tasks.md`
- Dry-run: `.specify/specs/006-daily-ai-signals/dry-run.md`
- Raw dry-run data and scripts (gitignored, not committed): `tmp/daily-signals-dryrun/`

## Decisions and why

1. **Separate DeepSeek call per article** (`daily-signals-extract-2`), not an extension of the summary
   call: keeps the digest's pinned prompts and journal replays intact, isolates failures, allows history
   backfill. Extra cost ~$0.02/day. Batching was used only in the dry-run to fit the call budget.
2. **Entity-level `is_new` flag + primary role** gate New. The v1 prompt (article-level novelty only)
   listed Volvo, Epic Games Launcher, Google Earth AI, SageMaker JumpStart as New; v2 removed this class
   of errors on the one day it was tested.
3. **Globally unique canonical key** (compact, packaging-stripped) with vendor-strip aliases; never
   auto-merge on fuzzy evidence; merge candidates + operator CLI.
4. **Deterministic story clustering** (shared primary non-company entity + event family, conservative
   company rule, simhash safety net). Treating `model_release`/`product_launch` as one family fixed all
   observed splits.
5. **Comparable data starts 2026-10-10** (first grounded `daily-publish` digest). Legacy digests are
   history-only for "first seen"; never in Rising/Cooling/spike baselines. Full Rising from 2026-10-23,
   spikes from 2026-10-13, Cooling hidden until then.
6. **Volume-adjusted Rising/Cooling** (daily volume tripled in October) and spikes need >= 2 publishers.
7. **Event counts per story**, not per article (a release covered 9 times is one release).
8. **Job integration**: second command in `run_daily_digest_job.sh`, after a successful
   `daily-publish`, same flock, exit status ignored; separate tables; kill switch
   `AINEWS_DAILY_SIGNALS_ENABLED` default false.
9. **UI**: server-rendered block inside the hero before the digest groups, JS re-render on date change,
   English, Cooling collapsed and hidden until 14 comparable days, chips display-only by default.
10. **Guarded migration** (`has_table` checks) because `deploy_prod.sh` starts the app before
    `alembic upgrade head` and routes call `create_all()`.

## Proposed spec changes (detail in plan.md "Spec Deltas")

SD1 legacy history-only scope; SD2 spikes-only Rising and hidden Cooling during building_history;
SD3 SC-002 rewrite (Beam first appeared 2026-10-05, a legacy day, so it is correctly not New on
2026-10-16 - it shows as a spike and top story instead); SD4 add `is_new`, `hardware`, `policy`;
SD5 New gate = primary + `is_new`; SD6 events per story; SD7 volume adjustment, spike publisher floor;
SD8 global canonical key; SD9 weekly preview needs no move; SD10 SC-001 judged with v2.

## Dry-run highlights

- 39 of 40 allowed provider calls, ~$0.17, 369 articles over 2026-10-12..16 (+90 re-extracted with v2).
- New, 40 displayed items: 22 OK, 12 uncertain, 6 bad (5 of the bad ones on v1-prompt days).
  Good catches: Muse Wonder (10-12), Muse Spark Open, Nemotron 3.5 Super VL, FLUX 3 Image Klein (10-15),
  Glimpse, GPT-Rosalind, MAI-Base-2 (10-16).
- Top stories: no duplicate events after tuning; one borderline over-merge (RTX Spark / Surface, 10-16).
- Spikes: Beam and Reflection AI on 10-16 (4 publishers each, trailing mean 0).
- Rising/Cooling: not computable yet (no 14 comparable days) - thresholds are spec defaults plus volume
  adjustment, flagged as unvalidated with a re-tune task after 2026-10-30.

## Open questions for the owner

1. Approve the legacy history-only backfill (~2,072 articles, ~$1.2 one-off) so New is meaningful from
   day one? Without it, New is relative to history since 2026-10-10 only.
2. Approve the one-line `docker-compose.prod.yml` change for the kill switch (default false), and who
   flips `AINEWS_DAILY_SIGNALS_ENABLED=true` on the server after the backfill review.
3. Approve Phase 7 validation spend (~$1.2 for the full 75-day local backfill, or ~$0.35 minimum).
4. Open Q4: should event chips filter the digest list in this iteration (optional task T6.4)?
5. Should established companies that appear for the first time in the corpus ever be shown as New
   (the plan says no unless the article presents them as new, e.g. founded / out of stealth)?
6. Accept SD3 (SC-002 rewrite) and SD4 (new entity types)?

## Risks (top)

Entity duplicates/aliases; generic or non-AI items in New (v2 tested on one day only); short comparable
history until 2026-10-23; provider outage (handled as partial, digest unaffected); cost (bounded,
~$0.08/day); SQLite vs PostgreSQL (portable DDL, guarded migration, manual PG check in rollout); page
performance (one indexed row read). Full table in plan.md.

## Not verified

- The production single-article prompt was not run; the dry-run used 12-article batches with
  1,500-character excerpts.
- v2 prompt on 4 of 5 days; Rising/Cooling on any day; PostgreSQL migration; page rendering and
  performance; job script behaviour on the server.
- Production DB contents were not read directly: inputs were the public digest API plus the local
  SQLite copy (all 369 target URLs matched locally; local digests themselves are stale and were not used).

## Side observation (out of scope, not changed)

`POST /api/news/digests` and `POST /api/news/weekly-analytics` are reachable without auth when auth is
enabled, because `auth_middleware` allowlists paths regardless of method (`src/app/web/app.py`,
`is_public_news_api`). Worth a separate fix.
