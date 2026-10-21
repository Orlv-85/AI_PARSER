# Review: source onboarding feature doc, PR #75 (2026-10-21)

Reviewer: a different session from the author (prompt: `docs/prompt-onboarding-doc-review-2026-10-21.md`).
Scope: `src/app/core/sources/onboarding.md` against `core/sources/onboarding.py`, `core/sources/review.py`,
`web/source_intake.py`, `web/routes/sources.py`, `SourceOnboardingService` in `web/service.py`,
`storage/source_candidate_repo.py`, `storage/source_repo.py`, the 99 tests the doc names (bodies read),
`specs/003-*`, `specs/011-*`, PR #8.

Checks: `scripts/check_code_docs.py` and `--diff origin/master --strict`: ok before and after the fix.

## Findings fixed in the doc

| Where (doc section) | What was wrong | Evidence |
| --- | --- | --- |
| Decisions, cache row | "decided (agent): 7 days" - the source exists | PR #8 body: "unchanged successful reviews are reused for seven days" |
| Decisions, new source defaults | "1.0 is the neutral weight of `rank_score`" - it is the top of the clamp | `core/ingestion/scoring.py:93`; new reason: `SourceConfig` field defaults (`config/sources.py:38,40`) |
| Decisions, edit row | "a running check never overwrites an edited candidate" - only URL or raw input are compared, a type-only edit is overwritten | `web/source_intake.py:177-179` |
| Check, cache | rule did not say the age is from `validated_at`, which a cache hit renews | `web/source_intake.py:146-149`, `:187` |
| Check, cache | "fallback review never reused" was credited to `test_stale_cache_rechecks_and_missing_provider_is_not_cached`; the test only checks expiry | `tests/unit/test_source_intake.py:84` |
| Check, registry duplicates | "earlier candidate of the batch": only drafts are compared; that case has no test | `web/source_intake.py:98-100,123` |
| Check, same host | final host is compared only with `sources`, not with batch drafts | `web/source_intake.py:151-153` |
| Check | "Only draft candidates are checked" had tests listed that do not check it | no test filters non-draft rows |
| Validation | missing: any status is validated (approved too); unknown ids skipped; nav/footer and excluded URLs skipped by link extraction | `onboarding.py:545`, `ingest/html.py:87-93` |
| Review actions, approve | missing: a reused source gets the candidate's URL, type and name; duplicate link cleared | `storage/source_repo.py:85-115`, `onboarding.py:656` |
| Review actions, reject | the doc stated the bug as the rule ("source stays enabled"); named tests reject drafts only | 003 spec US3 scenario 1: "rejected candidates remain excluded from fetch" |
| Review actions, mark duplicate | copying the target's `approved_source_id` stated as the rule; no test checks it | `onboarding.py:702` |
| Lists and summaries | missing: pending = draft only, disabled not counted, `rejected_count` is import rejections, empty filter summarizes all candidates | `storage/source_candidate_repo.py:264-291`, `web/service.py:549-568` |
| Into collection | YAML upsert resets name, type, URL, enabled, interval, weight (by key), not only `enabled` | `storage/source_repo.py:36-46` |
| Invariants | added: the check never changes a `sources` row | `web/source_intake.py:173-190`; 011 registry repair |
| Code map | 13 routes -> 14 | `web/routes/sources.py`, 14 `@router.` |
| Code map, patch targets | missing `sources_routes.import_source_candidates`, `review_candidate_overlaps` | `tests/unit/test_web_source_onboarding_api.py:358,510` |
| Code map | dead code listed (only `classify_candidate_batch` was named) | grep: no caller in `src/` or `scripts/` |

Checked and correct: Import rules and limits, normalization, overlap groups, probe bounds and public
address checks, model routing and thresholds, bulk approval, edit reset, access, export; the split
table places every top-level name of `onboarding.py` exactly once with no import cycle; the
`SourceCandidateRepo` 5x patch split (4 validation, 1 overlaps) and importer counts (6/1/10) match.

## Code differs from the intended rule (not fixed: doc-only PR)

| # | Code | Intended | Impact |
| --- | --- | --- | --- |
| 1 | `onboarding.py:662-664` reject keeps the source enabled | 003 US3: rejected stays out of fetch | articles keep coming from a rejected source |
| 2 | `onboarding.py:702` mark duplicate copies the target's source id | a candidate acts only on its own source (decided 2026-10-21, agent) | Disable on a duplicate (shown in admin, `index.html:1175`) turns off the target's source; API approve of a duplicate rewrites the target's URL (`source_repo.py:85-100`; the admin page blocks it, `index.html:1173`) |
| 3 | `source_intake.py:146-149,187` cache age from `validated_at`, renewed on hit | 7 days from the model call (PR #8) | a review re-checked weekly is never refreshed |
| 4 | `source_intake.py:158-160` caches a Jev `review` whose DeepSeek call failed or hit the budget | cache successful decisions only (011) | DeepSeek is not asked again for 7 days; the candidate stays manual |
| 5 | `onboarding.py:979-988` HTML validation passes any page with one non-nav link | 003 plan C: article links, quality scored | a homepage can be `validated` and approved by hand (the Check path is strict, `review.py:109-125`) |
| 6 | `source_candidate_repo.py:289` counts status `validated` | candidate statuses are draft/approved/rejected/disabled/duplicate | dead branch, no visible effect |

## Author's list, verdicts

| Item | Verdict | Evidence |
| --- | --- | --- |
| `classify_candidate_batch` dead | confirmed | `onboarding.py:224`; tests only |
| `write_approved_sources_yaml_snapshot` dead | confirmed | `onboarding.py:635`; helper writes the file itself (`scripts/sources_onboarding_helper.py:630-646`) |
| `SourceCandidateRepo.update_candidate` dead | confirmed | `source_candidate_repo.py:200`; edit goes through `_edit_candidate` |
| `create_import_batch` dead | confirmed | `source_candidate_repo.py:18` |
| `insert_normalized_draft_candidates` dead | confirmed | `source_candidate_repo.py:125` |
| reject leaves source enabled | confirmed, contradicts 003 | item 1 above |
| disabling a duplicate disables the target's source | confirmed, wider: also approve rewrites the target's URL | item 2 above |
| HTML validation accepts any page with a link | confirmed with nuance (nav/footer and excluded URLs skipped) | item 5 above |
| `summarize_batch` counts a status no candidate gets | confirmed | item 6 above |
| two "decided (agent)" | cache: refuted (PR #8 states 7 days); defaults: kept, reason corrected | Decisions table |

## Owner questions

- Reject of an already approved source: should rejecting it also stop collecting from it (as spec 003
  says)? Recommendation: yes.
- Check cache: should a failed or budget-skipped DeepSeek second opinion be retried on the next Check
  (more paid calls, at most the existing budget of 50 per check)? Recommendation: yes.
