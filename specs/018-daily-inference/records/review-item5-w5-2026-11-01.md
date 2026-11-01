# Review: PR #188, spec 018 item 5 W5 (2026-11-01)

Reviewer: background agent (model sonnet), read-only, worktree of `origin/feat/018-world-w5-jev`
at 497753e. Saved by the coordinator.

## Verdict: merge after fixes

## Must fix

1. **$0.10 per real day does not hold.** `open_world_assessor` uses `data/world/<D>/journal-world-stream-1-<cap>.sqlite3`;
   `PilotJournal` caps only inside one file. Real-day spend exceeds $0.10 with different
   `--max-usd` (confirmed by a run), with runs for D and D+1 on the same real day (catch-up), and
   after a 5xx wedges a journal (confirmed with a fake 500: every rerun stops with
   `unknown_or_failed_previous_call_requires_review`; `world_change.md` advises a different
   `--max-usd`, which opens a new $0.10). Steps A and B share one journal (fine).
   Fix: journal keyed by the real UTC run date with a fixed cap `WORLD_JEV_MAX_USD_PER_DAY`;
   `--max-usd` only a run-local lower limit against `total_committed_usd`; test that runs for
   different D and different `--max-usd` on one real day stay within $0.10; fix the `world.md`
   Cost cap and Decisions text and the wedged-journal advice for the world stream.
2. **Failure requeue weaker than documented.** With a journal, 5xx or outage is a journal stop, not
   a Jev failure; "Jev failure marks only the representative" fires only for a bad answer. Tests of
   the failure case use no journal. Document in `world.md`.

## Nice to have

- `test_cli_world_screen_rejects_max_usd_above_cap` passes by accident (missing-key exit 2 also
  prints "cap"): set a key, assert no journal file and no request.
- A late outlet of a screened cluster is screened again (paid) and may come back `in` while peers
  are `out`, giving a duplicate story in the top N.
- Top N is per window (D-1, D), not exactly per day across sliding windows; fine for W5.
- crapper: no CC >= 10; dryer: no duplicates.

## Mutations (`test_world_screen.py` + `test_world_storage.py`)

25 hand mutations; survivors that matter: (4) dry-run top N `top_n+1`, (13) rank representative
`min` -> `max`, (19) CLI `--max-usd` above-cap check removed. Equivalent survivors: (15) journal
stop check at loop top, (24) commit per screen item, (25) dry-run requeue (uncommitted).

## Checks run

pytest on world_screen, world_storage, world_change, deepseek_digest: 141 passed; ruff clean;
`check_code_docs.py --diff origin/master --strict` exit 0. Full suite and `make lint` not run by
the reviewer.

## Re-review of fix commit 9e07be3

Verdict: merge after one small fix; money closed.

- Must fix: `check_code_docs.py --diff origin/master --strict` exits 1: `pipeline.md` covers
  `provider_journal.py`, changed (`PilotJournal.committed_usd()`) without the doc.
- Money: different `--max-usd`, D and D+1, rerun after 5xx all stay within $0.10 per UTC day.
  `committed_usd()` sums `committed` (reservations and unknown calls included; conservative, right).
  Run limit checked before each request (can overshoot `--max-usd` by one request; journal cap
  holds). Midnight: day read once at journal open (acceptable).
- Wedged-journal procedure: `cost_usd` understates spend (unknown calls count 0); use
  `total_committed_usd`; do not delete the file, rename it `...reviewed-<time>`; the lowered limit
  applies to every further run that day. Or wait for the next UTC day.
- Mutations: 15 run; survivors: run limit `>=` -> `>`, run limit ignored in step B, known reference
  newest instead of oldest, `committed_usd` using `actual` instead of `committed`. First review's
  survivors 4, 13, 19 now killed.
- Checks: scoped pytest 148 passed; ruff clean.
