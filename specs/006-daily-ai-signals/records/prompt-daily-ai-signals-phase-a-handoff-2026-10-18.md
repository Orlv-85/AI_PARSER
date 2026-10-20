# Handoff: Daily AI Signals Phase A -> coordinator (2026-10-18)

**Plan is ready ("plan gotov").** Phase A (planning only) is finished. Please review the four files.

## Files to review

1. `specs/006-daily-ai-signals/plan.md` - revision 4
2. `specs/006-daily-ai-signals/tasks.md`
3. `specs/006-daily-ai-signals/dry-run.md`
4. `specs/006-daily-ai-signals/records/daily-ai-signals-phase-a-report-2026-10-17.md`

Branch `feat/006-daily-ai-signals`: revision 1 is commit `22f3b67`; revision 4 is in a follow-up commit
(only these four files). Spec `spec.md` unchanged; proposed changes are in plan.md "Spec Deltas" SD1-SD13.

## How the plan got here (three independent reviews, read-only, fresh sessions)

| Review | Verdict | Main points | File (local, uncommitted) |
| --- | --- | --- | --- |
| 1 (rev 1) | rework | global name key merged homonyms/versions; PilotJournal unfit; cost arithmetic; scope/stale snapshots; impossible test; dry-run verdicts too generous | `specs/006-daily-ai-signals/records/daily-ai-signals-phase-a-review-2026-10-18.md` |
| 2 (rev 2) | rework | order-dependent identity; family rules; fingerprint gaps; no hard deadline; $2.50 cap not enforced; missing vs empty days | `specs/006-daily-ai-signals/records/daily-ai-signals-phase-a-review2-2026-10-18.md` |
| 3 (rev 3) | rework (narrow) | vendor spellings split Gemini 4 Argon and the 10-13 story; version bump erased history; overrides on derived keys; vendor-dependent base key; SQLite id reuse | `specs/006-daily-ai-signals/records/daily-ai-signals-phase-a-review3-2026-10-18.md` |

Review 3 closed 10 of 15 review-2 findings fully and 5 partially, reopened none of review 1, and said no
major finding needs an owner decision. Revision 4 addresses T01-T20 (plan.md "Review Response").
Revision 4 itself has not been reviewed; the coordinator may want a short closure check of T01-T20.

## Key decisions (short)

- One DeepSeek call per article (`daily-signals-extract-3`) via a new signals ledger: one POST per
  attempt, 80 s watchdog, run / scope-day / budget-id USD caps checked before every POST.
- Mentions stored as evidence (no FK, survives retention); entities derived by a pure, order-independent
  reconciliation (vendor classes, vendor-prefix stripping, type groups, overrides with stable selectors).
- Comparable data from 2026-10-10; legacy digests are first-seen evidence only; per-section readiness
  (spikes from 3 complete days with >= 10 items; Rising/Cooling earliest 2026-10-23).
- Strict-majority story clustering on resolution keys; full in-memory recompute of snapshots.
- Job: one lock, one budget, outer `timeout`; signals never affect the digest; flag default false.

## Dry-run facts

39 of 40 provider calls, $0.17, 2026-10-12..16. New (40 shown): 26 OK / 6 uncertain / 8 BAD by the
independent re-judgment. Beam first appears 2026-10-05 (legacy), so on 10-16 it is a spike/top story, not
New. Rising/Cooling not computable yet. Production prompt v3 was never run.

## Owner decisions needed before Phase B (defaults in plan.md "Owner Decisions Required")

| ID | Question | Default |
| --- | --- | --- |
| OD1 | What counts as "New"? (a) Do new named versions count (v1.1, ACEv2)? (b) Does the GA release of "X" after a known "X Preview" count? (c) Do ports / new platforms / integrations count? | (a) yes, (b) yes, (c) no; sizes/quantization/instruct are packaging, not New; retrospectives are not New |
| OD2 | Use legacy digests (before 2026-10-10) to suppress New? Show signals for legacy dates? | Suppress: yes. Legacy snapshots: no (so SC-002 for Beam is reworded, SD3) |
| OD3 | Rising/Cooling only with two 7-day windows of >= 6 complete days each (spikes-only before), compared against volume-adjusted expectation? | Yes / yes; raw counts shown in UI |
| OD4 | Should event chips filter the digest now? | No, display-only (optional task T6.4) |
| OD5 | Budgets: validation $2.50 (stage 1: v3 on 5 days ~$0.35; stage 2: history ~$1.6; one prompt revision fits, more ~$5); production backfill ~$2.0; who flips `AINEWS_DAILY_SIGNALS_ENABLED`; approve the one-line `docker-compose.prod.yml` change? | $2.50 validation; prod backfill approved separately; owner flips the flag |
| OD6 | Keep first-seen evidence of deleted articles (retention, non-news cleanup) until purged by the operator? | Yes; corrections of existing articles replace evidence |
| OD7 | Thresholds as code constants (change = release + methodology version), not runtime-configurable? | Yes (narrower than FR-008 "configurable") |

Spec deltas needing acceptance: SD1-SD13 (plan.md). Most map to OD1-OD7; SD4 (new fields `is_new`,
`is_new_quote`, types `hardware`, `policy`) and SD6 (event counts per story) are standalone.

## Not verified

Prompt v3; revision-4 identity rules end-to-end on real data; Rising/Cooling; PostgreSQL migration and
prune; UI rendering and performance; job script on the server. No tests or lint were run (no code).

## Side observations (out of scope)

- `POST /api/news/digests` and `POST /api/news/weekly-analytics` bypass auth (path-based allowlist).
- `docs/configuration.md` says migrations run before the app starts; `deploy_prod.sh` starts the app first.
