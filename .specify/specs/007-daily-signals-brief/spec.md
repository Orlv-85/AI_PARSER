# Feature Specification: Daily Signals Brief and Readability (006 iteration 2)

**Feature Branch**: `007-daily-signals-brief`
**Created**: 2026-10-19
**Status**: Draft (direction agreed with the owner)
**Builds on**: `.specify/specs/006-daily-ai-signals/` (spec, plan, dry-run), merged in PR #39, live in
production since 2026-10-19 (backfill 2026-08-03..10-18 done).
**Input**: Owner review of the live block on `/?date=2026-10-16` (RU, paraphrased): "Is there no
summary? How informative is this?" Coordinator assessment: the data is correct, but the block lists
names and counters without saying what they are or why they matter.

## Problem Context

What the live block shows today (2026-10-16 example):

- **New** items as `name | type | vendor | N source(s)` with an `early signal` badge on almost every
  item; to learn what "MAI-Base-2" is, the reader must open "sources" and leave the page. The digest
  already has grounded English summaries for the same articles; they are not used in the block.
- `variant of GPT` appears for GPT-Live-1.1: the token-prefix parent is a generic family word, not a
  specific earlier model.
- **Spikes** duplicate each other and Top stories (Beam and Reflection are one event; Surface Laptop
  Ultra is also a top story) and do not say why something spiked ("today 4 vs 0/day").
- **Event chips** ("11 analysis", "5 other") are counts the reader cannot act on (display-only, OD4).
- **Quiet days** (weekends, e.g. 2026-10-17/18 with 14 items) render an almost empty block that looks
  broken.
- There is **no narrative**: nothing answers "what happened in AI yesterday" in a few sentences.

## Goals

- G1. A short **daily brief** at the top of the block: 3-5 grounded sentences on the most important
  events of D, each with links, readable in under 30 seconds.
- G2. Every New item says **what it is** in one line.
- G3. Less noise: badges, variants, duplicate spikes and empty states carry information or disappear.
- G4. Same guarantees as 006: no provider calls on page load, bounded cost, deterministic and cached
  where possible, a failure never breaks `/` or the digest job.

## Non-Goals

- Weekly/monthly analytics (next spec), Jev second opinion (`docs/jev-novelty-second-opinion-todo.json`),
  article archive (`docs/article-archive-todo.json`), video/Telegram outputs.
- Changing extraction (prompt `daily-signals-extract-5`), identity rules, New gate thresholds or
  Rising/Cooling math, except where FR-005/FR-006 below require display-level changes.

## User Scenarios

### US1 - Read the day in 30 seconds (P1)
As a reader I open `/` and see "Today in AI" with 3-5 sentences: the main releases/events, why they
stand out (only from source facts: e.g. "open weights", "first model", "N outlets covered it"), each
sentence linking to its sources.

Acceptance:
1. Given a normal day (>= 2 multi-publisher stories or >= 3 New items), the brief has 3-5 sentences,
   each citing at least one article of D; no sentence contains a fact absent from the supplied inputs.
2. Given a quiet day, the brief says so in one sentence with the counts ("Quiet day: 14 items, no story
   covered by more than one outlet") plus at most 2 sentences on what did happen.
3. Given generation failed or is unavailable, the block shows the rest as today with no brief and no
   error text beyond a muted line.

### US2 - Know what each new thing is (P1)
Each New item shows one line (<= 140 chars) describing it, taken from grounded material: the digest
summary of its primary article or the novelty quote; never invented.

### US3 - Less noise (P2)
- `early signal` is not a per-item badge; the item shows its source count; confirmed items (>= 2
  publishers) may be marked instead, or the list is split "Confirmed" / "Single source".
- `variant of X` is shown only when X is a specific earlier entity (contains a digit or more than one
  token, and is not a stoplisted/generic family word).
- A spike that is the same event as a top story, or a company spike whose product is also a spike/New/
  top story of D, is folded into that item (e.g. "Beam - 4 sources, spike") instead of a separate line.
- Spikes show their reason: the top linked story label.
- Event chips: keep only "hard" event types by default (releases, launches, funding, acquisitions,
  partnerships, regulation, legal, security, hardware, people moves); analysis/research/other folded
  into "+N more".

## Requirements

- **FR-001 Brief generation**: one provider call per day D after the snapshot is computed, input =
  the stored snapshot of D (top stories, New with one-liners, spikes, event counts) plus the digest
  summaries of the referenced articles, capped in bytes. Output JSON: 1-5 sentences, each with
  article ids from the input and a short exact supporting quote; validation like
  `core/weekly_narrative.py` (ids must exist, quotes must be substrings of supplied text, length caps,
  English, no instructions followed from article text). Invalid -> one recovery attempt -> otherwise
  no brief.
- **FR-002 Model and cost**: model configurable; default the current DeepSeek model. The planner may
  propose a stronger model for this single daily call if a 5-day comparison shows clearly better briefs;
  cost per day must stay under a cent at ledger prices for the default. Calls go through the existing
  signals ledger and per-run caps; cached by input hash and prompt version.
- **FR-003 Storage and versioning**: the brief is stored with the snapshot (or alongside it) with its
  prompt version and input hash; recompute without changed inputs never regenerates it; a changed
  snapshot regenerates it on the next paid run (not on page load). Backfill command can generate briefs
  for past comparable days within a budget.
- **FR-004 One-liners**: deterministic, no new provider call: the first sentence of the digest summary
  of the entity's primary New article (cleaned, truncated at a word boundary to 140 chars), else the
  novelty quote. Stored in the snapshot payload; escaped on render.
- **FR-005 Noise rules**: US3 rules implemented in compute/view; thresholds and lists as constants
  recorded in the snapshot; methodology version bump.
- **FR-006 Quiet day state**: a day with fewer than 20 items or no multi-publisher story renders a
  compact block (brief + New if any + counts), not empty cards.
- **FR-007 API/UI**: `DailySignalsResponse` gains optional fields (`brief`, per-item `one_liner`,
  spike `reason`); existing fields unchanged (backward compatible). The page renders the brief first;
  mobile layout and escaping rules as in 006.
- **FR-008 Job**: brief generation runs inside the existing `daily-signals` step (same lock, budget,
  timeout, isolation). `AINEWS_DAILY_SIGNALS_ENABLED` gates it like extraction.

## Success Criteria

- SC-001: On 2026-10-12..18 (production data copy), every brief sentence is supported by its quotes
  (manual check), no hallucinated names/numbers, quiet days handled per US1-2.
- SC-002: Every displayed New item has a one-liner; no invented content (spot check all items on the
  7 days).
- SC-003: On 2026-10-16 the block no longer shows `variant of GPT`, separate Beam/Reflection spikes, or
  per-item `early signal` badges.
- SC-004: Page load makes no provider calls; `/` stays 200 with a corrupt or missing brief.
- SC-005: Daily cost increase <= $0.01 at ledger prices with the default model.
- SC-006: Repo gate passes (`make lint`, full pytest incl. PostgreSQL as in CI).

## Open Questions (planner proposes, owner decides)

1. Brief language: English (site language) by default; Russian as an option later?
2. Stronger model for the brief only (cost vs quality, measured on 5 days)?
3. Split New into "Confirmed" / "Single source" vs a single list with source counts.
