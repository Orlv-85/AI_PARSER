# Review: PR #190, spec 018 item 5 W6 (2026-11-01)

Reviewer: background agent (model sonnet), read-only. Saved by the coordinator.

## Verdict: merge after fixes

## Must fix

1. **World download overwrites archive metadata of real articles** (`world_text.py:63` `_documents`
   -> `archive_articles` -> `ArchiveRepo.upsert_document`, `archive.py:35-48`). A world URL equal
   to an archived article's URL sets its `article_id` and `source_key` to None (reproduced). The
   nightly job re-syncs only 7 days; `archive purge --source` is affected. Fix: create documents only
   for hashes without an `ArchiveDocument`; test with a pre-existing real document.
2. **World documents change the nightly job's numbers and budget.** `gave_up` world documents count
   in `window_states` / `coverage_pct` (operator target 90, `docs/deploy.md:346`); retryable
   failures stay `failed` in the archive and the nightly job retries them (probe: 30 same-host HTTP
   500 world documents took the 20-per-host cap, 10 real ones `skipped_cap`; 100 would take half of
   `ARCHIVE_MAX_DOWNLOADS`). Fix: marker (for example `source_key="world"`), excluded from
   `window_states` and from `due()` when `ids` is None; docs and tests.

## Nice to have

- N bound is per run; across reruns a fully `no_text` cluster leaves the top and the next enters.
- A `failed` document with a future `next_attempt_at` keeps the candidate `screened_in` up to 7
  days, blocking fallback to the next outlet.
- Untested: early give-up branch (M14 survived), "next run tries the next outlet", ranking of
  `no_text` clusters (M10 killed only by the CLI summary test).
- Long doc lines; `world texts` has no time limit (W7: host lock).

## Holds

Nightly path unchanged without `only`/`ids`; ER-9/FR-016; robots, bot agent, pacing, outage from
the archive code (M19 killed); state changes; dry run; not wired; docs match apart from gaps.

## Mutations

18 run, 16 killed; survived M12 (equivalent) and M14 (give-up branch untested).

## Checks

CI pass; 87 passed on the four test files, 221 on `-k "archive or world"`; ruff clean;
`check_code_docs.py --strict` exit 0.

## Re-review of fix commits 34524f3, a343dcd

Verdict: merge. No path rewrites a real document (download adds versions and attempts only);
marker set in the same transaction (one commit; rollback mutation killed); only `purge` and the new
`_not_world()` read `source_key`; nightly path unchanged for NULL/real keys; takeover by a real
article works; fallback rules hold.

Nice to have: `status` (`state_counts`, `hosts_without_text`, `capture.py:358-366`) still counts
world documents; mutation B7 (download every non-archived document, not only `pending`) survived;
a real article document in `failed` becomes `no_text` at once (documented).

Mutations: 12 run, 11 killed (earlier survivor M14 now killed), B7 survived. Checks: CI pass;
228 passed on `-k "archive or world"`; ruff clean; `check_code_docs.py --strict` exit 0.
