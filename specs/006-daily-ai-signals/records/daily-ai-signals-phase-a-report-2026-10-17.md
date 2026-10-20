# Daily AI Signals - Phase A Report (2026-10-17; revisions 2-4 on 2026-10-18)

For: coordinator session. Scope: planning only; no production code, migrations or tests were written.

Deliverables:

- Plan (revision 4): `specs/006-daily-ai-signals/plan.md`
- Tasks: `specs/006-daily-ai-signals/tasks.md`
- Dry-run: `specs/006-daily-ai-signals/dry-run.md`
- Raw dry-run data, scripts and test fixtures (gitignored, not committed): `tmp/daily-signals-dryrun/`

Revision 2 addressed review 1 ("rework"; R01-R17). Revision 3 addresses review 2 ("rework"; S01-S15:
order-dependent identity, family rules, snapshot invalidation, hard deadline, validation budget,
missing vs empty days, quote overclaim, wrong-history stickiness, ledger accounting). Revision 4
addresses review 3 ("rework", narrow; T01-T20: vendor spellings splitting entities and stories, version
bumps erasing history, overrides keyed on derived keys, vendor-dependent base keys, article id reuse).
All are mapped in plan.md "Review Response".

## Decisions and why

1. **Separate DeepSeek call per article** (`daily-signals-extract-3`): keeps digest prompts and replays
   intact, isolates failures, allows history backfill. Cost ~$0.06-0.09 per day.
2. **New signals ledger instead of `PilotJournal`**: one physical POST per dispatch with a hard
   streaming deadline; run, scope-day and budget-id USD caps checked atomically before every POST;
   usage accounted on any status; bounded automatic recovery; new request keys for deliberate retries.
3. **Entities are derived** from stored mention evidence by a pure, order-independent reconciliation:
   versions/sizes kept; vendor spellings grouped into classes (Google ~ Google DeepMind); vendor prefixes
   stripped regardless of the vendor field; type groups separate homonyms; genuinely different vendors
   split, with a review entity only when no vendor dominates; overrides use stable selectors and
   `manual:<n>` targets.
4. **New** (default, owner decision OD1): first appearance in the corpus of an entity an article
   presents as newly announced/released, with a grounded launch quote; named versions count, packaging
   variants, ports, features and retrospectives do not.
5. **Strict-majority story clustering** with event families, both-primary entity rule and same-family
   simhash; removed the RTX Spark/Surface over-merge without breaking large stories.
6. **Comparable data from 2026-10-10**; legacy digests are history-only evidence; explicit day states
   (missing vs observed empty vs incomplete); **per-section readiness** (spikes from 3 complete days,
   Rising/Cooling from two 7-day windows with >= 6 complete days each).
7. **Full in-memory recompute** of all comparable days after every run or entity command; reports
   written when their payload hash changes.
8. **Retention-safe evidence**: derived tables cascade with articles; the mention-evidence table has no
   FK, so pruning keeps first-seen history while corrections of existing articles still apply.
9. **Job**: one host lock and one time budget; signals only after a successful publication, under an
   outer `timeout` with container cleanup; failure, timeout or skip never changes the job result; kill
   switch `AINEWS_DAILY_SIGNALS_ENABLED` default false (gates paid extraction only).
10. **UI**: server-rendered block before the digest groups, isolated read (signals errors never break
    `/`), JS re-render with an out-of-order guard; English; chips display-only.

## Owner decisions needed (defaults in plan "Owner Decisions Required")

1. OD1 - meaning of New (default above). Do new named versions count? Do ports/new platforms count?
   Previews: does the GA release of "X" after a known "X Preview" count as New (default yes)?
2. OD2 - legacy digests suppress New (default yes); snapshots for legacy dates (default no; this is why
   SC-002 for Beam needs rewording - Beam's first day is 2026-10-05).
3. OD3 - spikes-only Rising and hidden Cooling until two complete weeks; volume-adjusted comparison.
4. OD4 - event chips filter the digest now (optional T6.4) or later (default later).
5. OD5 - validation budget $2.50 in two stages (v3 on 5 target days ~$0.35, then history ~$1.6; one
   prompt revision fits, more needs ~$5), production backfill budget (~$2.0), who flips the flag;
   approval of the one-line `docker-compose.prod.yml` change.
6. OD6 - first-seen evidence of retention-deleted articles is kept; corrections of existing articles
   replace evidence (default).
7. OD7 - thresholds are code constants recorded in snapshots (narrower than FR-008 "configurable").

## Proposed spec changes

SD1 legacy history-only scope; SD2 per-section readiness; SD3 SC-002 rewording (or restore it on
2026-10-05 if legacy snapshots are wanted); SD4 `is_new`, `is_new_quote`, `hardware`, `policy`;
SD5 New definition per OD1; SD6 events per story; SD7 volume adjustment and spike publisher floor;
SD8 withdrawn; SD9 weekly preview needs no move; SD10 SC-001 judged with the final prompt and a
recall rubric; SD11 thresholds as code constants; SD12 first_seen from retained evidence; SD13 chips
display-only.

## Dry-run highlights

- 39 of 40 allowed provider calls, $0.170, 369 articles over 2026-10-12..16 (+90 re-extracted with v2).
- New, 40 displayed items: independent re-judgment 26 OK / 6 uncertain / 8 BAD (my original count
  22/12/6 was too generous: Microsoft-Decision-1 was already seen on 10-10; Moltbook and Attie are
  retrospective). v2 did not remove retrospective false positives; revision 2 adds rules and a grounded
  launch quote, untested until T7.2.
- Top stories: no duplicate events; average-link re-run removed the 10-16 over-merge.
- Spikes (2 days computable): Beam and Reflection AI on 10-16 (4 publishers each, trailing mean 0).
- Rising/Cooling: not computable yet; flagged unvalidated, re-tune after 2026-10-30.

## Risks (top)

Wrong merges or duplicates; retrospective/established items in New; short and patchy history; stale
snapshots; provider outage and unknown billing; cost; job timeout; retention conflicts; SQLite vs
PostgreSQL; migration race with `create_all()` (idempotent, not serialized; documented recovery); page
breakage (isolated read). Full table in plan.md.

## Not verified

- The production prompt v3 (single article, 6,000 chars, novelty quotes) was never run.
- Revision-3 reconciliation and day-state rules were not re-run end-to-end on the dry-run data
  (covered by tests and T7.2); clustering evidence uses old identity keys.
- Rising/Cooling on any day; recall; PostgreSQL migration and prune; page rendering and performance;
  job script on the server.
- Production DB was not read directly: inputs were the public digest API plus the local SQLite copy.

## Side observation (out of scope, not changed)

`POST /api/news/digests` and `POST /api/news/weekly-analytics` are reachable without auth when auth is
enabled, because `auth_middleware` allowlists paths regardless of method (`src/app/web/app.py`,
`is_public_news_api`). Worth a separate fix. Also `docs/configuration.md` says migrations run before
the app starts, but `scripts/deploy_prod.sh` starts the app first.
