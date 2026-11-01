# Report: spec 018 item 5, W5 Jev steps A and B (2026-11-01)

Implementer report (background agent, model sonnet), saved by the coordinator. PR #188, branch
`feat/018-world-w5-jev`. No paid calls (fakes only).

## Files

- New: `src/app/core/world/screen.py` (question, state, parser, priority; pure),
  `src/app/core/world_screen.py` (`run_screen`, `rank_clusters`, `open_world_assessor`,
  `TextSource`, `no_text`), `tests/unit/test_world_screen.py` (29 tests).
- Changed: `src/app/core/world/world.md` (doc first), `src/app/core/bulletin/world_change.py`/`.md`
  (`WorldChangeAssessor.ask`, `open_assessor(root, version, usage_event)`), `src/app/storage/world.py`
  (`candidates_in_window`, `set_priority`), `src/app/cli/main.py` (`world screen`),
  `tests/unit/test_world_storage.py`, `tests/unit/test_deepseek_digest.py` (04:00 job has no
  `world screen`).

## Checks (implementer)

`make lint`: ruff, mypy (250 files), pylint 10.00. Full pytest 1777 passed, 1 skipped.
`check_code_docs.py --diff origin/master --strict` exit 0. dryer: no duplicates; crapper max 9 in new
code. New tests seen failing first (import error).

## Findings

- Jev no-content: `jev.py` has no local check on empty `Content`; the daily path already sends empty
  `Content:` for feed items. Live acceptance of a title-only state is checked by the gate run.
- Cap: own `PilotJournal` file `data/world/<D>/journal-world-stream-1-<cap>.sqlite3`,
  `WORLD_JEV_MAX_USD_PER_DAY` $0.10 for A and B together; `--max-usd` can only lower it; at cap logs
  `world_cost_cap`, rest `not_attempted`. Test `test_world_journal_is_separate_from_digest_cap`.

## Decided by the implementer

- `--date D` = GDELT day; window D and D-1; budget day D; new subcommand `world screen`.
- `SCREEN_THRESHOLD = 0.5`, unmeasured.
- Cluster representative = oldest member; followers copy state and confidence; a late outlet of a
  screened cluster is screened again.
- Rank = `screen_confidence` x distinct source domains (themes not stored by W3).
- Already-assessed clusters rank first, so a window never asks more than `WORLD_TOP_N`.
- `last_error` prefix `screen:` / `assess:`; failed with fewer than `MAX_ATTEMPTS` (3) requeue on the
  next run; other prefixes (W6) untouched. Jev failure marks only the representative; journal stop
  marks nothing failed.
- `--dry-run` does not call the text seam; reports `retryable_failed` without requeue.
- Not wired into the 04:00 job; no timer.

## Gate run (after review; paid)

On a database holding a collected day: `ai-news world screen --date 2026-10-31 --dry-run`, then
without `--dry-run` (about 1,600 title requests). Measure: step A input tokens per request (plan
assumed 300), `in / screened` (threshold 0.5), `cost_usd` vs $0.03-0.04. Step B only after W6.

## Fixes after review (commit 9e07be3)

1. Money: world journal one file per real UTC day `data/world/<UTC today>/journal-world-stream-1.sqlite3`,
   fixed $0.10 cap; `open_world_assessor(settings, logger, today)` (clock injected); `--max-usd` a
   run limit only (`run_screen(..., limit_usd)`, stops before a request, logs `world_cost_cap`),
   rejected above $0.10. New `PilotJournal.committed_usd()`; `open_assessor` got `file_name`.
   Tests: `test_world_budget_is_per_real_day_across_dates_and_limits`,
   `test_world_next_real_day_gets_new_budget`, `test_world_run_limit_stops_before_request`.
2. Wedged journal: documented (bad answer marks the representative failed; HTTP/transport error is a
   journal stop, marks nothing); operator steps: review log line and journal, then wait for the next
   UTC day, or delete that day's file and rerun with `--max-usd` = $0.10 minus that day's spend.
   Test `test_world_wedged_journal_marks_nothing_failed` (real `PilotJournal`, fake 500).
3. Late outlet follows the oldest screened member of its cluster without a request
   (`test_late_outlet_follows_screened_cluster`; dry run `would_follow`).
4. Survivors: `test_dry_run_respects_top_n`,
   `test_rank_representative_prefers_assessed_then_text_ready_then_oldest`, CLI above-cap test sets a
   key and asserts no `data/` and no request. Mutation not re-run by the implementer.
5. Top N per window noted in Decisions.

Checks: `make lint` clean (mypy 250 files, pylint 10.00); full pytest 1784 passed, 1 skipped;
`check_code_docs.py --strict` ok.

## Second fixes (commit 316bf98)

- `pipeline.md`: `PilotJournal.committed_usd()` rule, test
  `test_journal_committed_usd_counts_reservations_and_unknown_calls`.
- `world.md` wedged-journal procedure: wait for the next UTC day, or rename the journal to
  `...reviewed-<UTC time>` and rerun with `--max-usd` = $0.10 minus `total_committed_usd` for every
  further run that day.
- Mutations killed by new tests: `committed_usd` on `actual`; run limit `>=` -> `>`
  (`test_world_run_limit_equal_to_spend_stops`, `test_world_run_limit_also_stops_step_b`); step B
  ignoring the run limit; late outlet following the newest member
  (`test_late_outlet_follows_oldest_screened_member`).
- Checks: `make lint` clean; full pytest 1788 passed, 1 skipped. Coordinator: CI lint (incl. code
  docs gate) and tests pass on 316bf98.
