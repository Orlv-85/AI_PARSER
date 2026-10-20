# Coordinator review: Daily AI Signals Phase A, plan revision 4 (2026-10-18)

Reviewed: `specs/006-daily-ai-signals/plan.md` (rev 4, commit ff6360e), `tasks.md`,
`dry-run.md`, `specs/006-daily-ai-signals/records/daily-ai-signals-phase-a-report-2026-10-17.md`, handoff file.

## Verdict

Approve the direction and the data findings. Before Phase B starts, change the delivery order and cut
scope for the first release. No fourth full review round: the remaining risk is product quality of
"New", which only real extraction output can answer.

## Strong points (keep)

- Data facts: comparable digests start 2026-10-10; legacy days only as first-seen evidence; Beam first
  seen 2026-10-05; hardware/policy types are needed.
- Isolation: signals run after the digest commit, flag default off, page and API never call providers,
  digest/weekly data untouched on every rollback path.
- Pure, order-independent reconciliation and full in-memory snapshot recompute with payload hash.
- Per-section readiness instead of "insufficient data" walls.

## Findings

### C1 (blocker for ordering): the core value is unvalidated and is validated last

New precision in the dry-run is 26 OK / 6 uncertain / 8 BAD of 40 (65%), on prompts v1/v2 with batched
1,500-char excerpts. Production prompt v3 (per article, quotes) was never run. Validation is Phase 7,
after storage, ledger, API, UI and job are built. If v3 does not reach acceptable precision, most of the
work is built on an unproven signal.

Required: a prompt gate as the first Phase B step. Run v3 per article on 2026-10-12..16 (~370 calls,
~$0.35, under the approved validation budget) with a throwaway script in `tmp/`, apply the T7.2 rubric,
and stop for owner review. Pass bar (proposed): New precision >= 80% OK, <= 10% BAD, no non-AI or
established-company items (Volvo, Black Forest Labs class), retrospectives rejected (Moltbook, Attie).
Up to two prompt revisions inside the $2.50 budget; otherwise stop and report.

### C2 (scope): first release is over-engineered relative to risk and cost

Typical day costs ~$0.08. Three review rounds each added machinery for edge cases. Proposed MVP cut
(defer, do not delete from the plan; mark as "Deferred" with the trigger that would bring them back):

- Ledger: keep one POST per attempt, replay of 200 responses, per-run caps (calls, USD from actual
  usage with a reservation, app-side deadline) and stop after 3 consecutive failures. Defer budget ids,
  lifetime per-scope-day USD cap, attempt keys/limits per content hash, `reset-attempts`, the 80 s
  watchdog thread (the job's outer `timeout` already bounds wall time; use httpx timeouts plus a
  per-attempt deadline check). Validation/backfill budgets are enforced by `--max-usd` per invocation.
- Entities: keep normalization, stoplist, vendor classes, base/family keys, pure reconcile, the shared
  `?` entity, and `merge` + `alias` overrides with stable selectors. Defer `split`,
  `ai_entity_candidates` and the `suspects` command (operator can query `needs_review` entities).
- Keep: evidence table without FK, (id, url_canonical_hash) identity, recompute, job script design,
  API/UI as planned.

Expected effect: noticeably fewer tables, modules and tests in the first PR(s), same user-visible
result.

### C3 (security, out of scope for 006, confirmed on production)

`POST /api/news/digests` and `POST /api/news/weekly-analytics` are in the public path allowlist
(`src/app/web/app.py` `auth_middleware`, `is_public_news_api` is path-only, not method-aware).
Production check with an empty JSON body: both return 422 (passed auth, failed validation), while
`POST /api/update/run` returns 401. Anyone can overwrite any day's public digest or weekly report.
`scripts/digest_generator.py` posts to both endpoints, so the fix needs an authenticated path for it.
Handle as a separate small fix before or in parallel with 006; do not bundle into 006.

### Minor

- M1: The weekly preview below the digest keeps showing broken legacy content (e.g. non-AI items as
  "Trending Down"). Out of scope; consider hiding it or reducing it to a link in a follow-up.
- M2: Review files and prompts from Phase A are untracked in `docs/`; commit them for history.

## Owner decisions (coordinator recommendation)

OD1-OD7: accept defaults. SD1-SD13: accept (SD4 `is_new`/`is_new_quote`, `hardware`/`policy`; SD6 event
counts per story). OD5: validation $2.50 approved; production backfill cap to be set by the owner;
one-line `docker-compose.prod.yml` change approved (flag default false); owner flips the flag.

## Next step

After owner answers: coordinator writes the Phase B prompt with C1 (prompt gate first, stop for
review) and C2 (MVP scope) applied; implementer updates plan.md/tasks.md accordingly as its first
commit.
