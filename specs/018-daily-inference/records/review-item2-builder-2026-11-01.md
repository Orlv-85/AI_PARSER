# Review: PR #192, spec 018 item 2 bulletin builder (2026-11-01)

Reviewer: background agent (model sonnet), read-only, worktree at 86d88ad. Saved by the coordinator.

## Verdict: merge after fixes

## Must fix

1. Headline cut at a comma (`builder.py` `make_headline`, `":,;"`): "CROSBY, AN AI-FIRST LAW FIRM*"
   is a verbless fragment. Fix: cut only after `:` or `;`, before a dash, or before
   but/while/because/although; no boundary -> skip the story; none fits -> no headline (item 3
   writes headlines). Update `test_long_headline_is_cut_at_a_clause_boundary` and `builder.md`.
2. Busy-day median includes `partial`/`unavailable` days (`bulletin_input.py` `_median_items`, no
   status filter), so ordinary days read as busy. Fix: filter by ready statuses; test.

## Nice to have

3. Area reactions imply facts ("Productivity grows.", "Capacity grows.", "Investment in the future
   continues.", "Knowledge advances.", "The Administration welcomes the dialogue."): a layoffs story
   would get "Productivity grows." `voice.md` forbids reactions implying a fact.
4. A strong `none` member drops the whole event: pick the representative among non-`none` members.
5. Harm with `world_change` `none` or below threshold is not counted in incidents: state it.
6. Dedup: hash-fallback articles miss the top-story key (`_digest_candidates`); world vs digest
   merge only by title key.
7. Unassessed digest articles dropped silently: log the assessed share.
8. `voice.md` still says "30-day median plus a quarter" without the 7-day minimum.
9. Numbers line has one variant (FR-004 variants by date).
10. Headline may skip a higher-scored story without a boundary: say so in the doc.

## Checked and OK

FR-003 caps and mapping; ER-11 harm exclusion; ER-4/ER-2 never-list on every phrase; reactions at
most one per story (two per issue in practice); Day 1429 = 2026-10-29; day type and skip reasons;
date-based variants (test not vacuous); switch default off; narrow FR-016 change; CLI dry run only.

## Mutations

31 run, 28 caught; survived: M18 (`issue` into Key results), M22 (plain line takes an AI-actor
issue), M26 (median window includes the day itself).

## Checks

51 passed on the builder and world storage tests; ruff clean; `check_code_docs.py --strict` exit 0.
