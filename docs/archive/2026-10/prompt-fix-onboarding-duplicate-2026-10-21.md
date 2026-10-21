# Prompt: a duplicate candidate acts only on its own source (2026-10-21)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first. This is the second task of the session that split
`core/sources/onboarding.py` (`docs/prompt-split-onboarding-2026-10-21.md`). Do it **after** the
split PR is open, as a separate PR: branch from the split branch, base the PR on the split branch
(GitHub retargets it to `master` when the split merges; rebase then if needed). Do not put this
change into the split PR.

## Context

`src/app/core/sources/onboarding.md`, rule "Mark duplicate", says: a candidate acts only on a
source it approved itself; the duplicate gets no `approved_source_id` of the target's. The code
differs (`_mark_duplicate_candidate`, the doc gives file:line): it copies the target's
`approved_source_id` (overwriting the candidate's own). Effects, confirmed by the PR #75 review:

1. "Disable" on a duplicate (the admin page offers it) disables the target's source, so the
   original source stops being collected.
2. "Approve" of a duplicate through the API rewrites the target's source URL, type and name
   (`SourceRepo.create_from_candidate` reuses the source by id); the admin page blocks this button
   for duplicates, the API does not.

The owner approved the fix on 2026-10-21. Production has no affected rows (checked read-only on
2026-10-21: 10 duplicates, none with `approved_source_id`), so no data migration.

## Change

- Marking a duplicate keeps the candidate's own `approved_source_id` (none for a draft) and never
  copies the target's.
- "Approve" of a candidate with status `duplicate` is refused like other invalid review actions
  (same error shape and HTTP status as the existing invalid-action responses), matching the admin
  page; say which response you reused.
- "Disable" of a duplicate without its own approved source is refused the same way as disabling a
  candidate without `approved_source_id` today (there is a test for that case).
- Doc first: edit the "Mark duplicate" rule in `onboarding.md` (remove "Code differs", state the
  approve and disable outcomes for a duplicate, name the new tests), then code and tests.

## Tests

- Marking a draft and an approved candidate as duplicate: the target's `approved_source_id` is not
  copied; an approved candidate keeps its own.
- Disable on a duplicate does not touch the target's source (`sources.enabled` of the target stays
  true).
- API approve of a duplicate is refused and the target's source row is unchanged.
- Each new test must fail on the code before the fix (check it, say so).

## Checks

Full gate: `make lint PYTHON=...`, full `pytest`, `scripts/check_code_docs.py` and
`--diff <base> --strict`.

## Output

One PR, do not merge. In your reply: the PR link; the responses reused for refused actions; tests
added and proof they failed before; exact checks with pass counts; open questions one line each
(how settled, or a yes/no question for the owner with a recommendation).
