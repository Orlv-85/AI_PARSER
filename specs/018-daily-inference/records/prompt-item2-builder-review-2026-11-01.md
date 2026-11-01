# Prompt: review of PR #192 (018 item 2, bulletin builder) (2026-11-01)

You review PR #192 (`feat/018-bulletin-builder`). You did not write it. **Read-only: no commits,
pushes, merges, PR comments, paid calls, network or production access.** Never run any command that
changes `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself (no `gh pr checkout`, no `git checkout`
there); you may read files there. Report in English.

## Read

- `gh pr view 192`, `gh pr diff 192`, `gh pr checks 192`.
- Implementer worktree (do not edit it): `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.claude/worktrees/agent-a9819038b5910c0e5`.
  For runs and mutations, create a worktree of `origin/feat/018-bulletin-builder` under your
  scratchpad named with `pr192`; never remove one you did not create; remove yours at the end.
- `AGENTS.md`; `specs/018-daily-inference/spec.md` (ER-1..ER-12, User Story 1, FR-001..FR-006,
  FR-016) and `voice.md`; item prompt `records/prompt-item2-builder-2026-11-01.md` (on the branch).
- Implementer report (judge each decision):
  `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/coord-records/specs/018-daily-inference/records/report-item2-builder-2026-11-01.md`.

## Check

1. Editorial rules in code: FR-003 mapping and caps (Key results 4, launches 2, one rubric,
   Cooperation 2, incidents counted), ER-11 harm never headline / rubric / reaction, ER-4 never-words
   check on all phrases, ER-2 (no "Administration released"), reactions at most one per story and
   three per issue, no reaction implying a fact.
2. Headline (FR-004, ER-8): selection (confidence x outlets among shown stories, never harm), the
   8-word cut at a clause boundary. The fixture gave "CROSBY, AN AI-FIRST LAW FIRM*": judge whether
   a cut at a comma that leaves no verb is acceptable; propose the smallest rule (for example only
   cut at colon, dash or semicolon, else use the full title if it fits a looser limit, else no
   headline). Note item 3 (model writer) will write headlines; this is the title-only fallback.
3. Day type: quiet, busy (7-day history rule vs `voice.md` "30-day median plus a quarter"),
   partial/unavailable -> skipped with reason; `no_assessments` vs quiet.
4. Phrase choice by date: neighbouring days differ (test not vacuous); JSON loader validation;
   `voice.md` now points to the JSON with no phrase copy left.
5. Dedup into events and ranking; the switch `AINEWS_WORLD_STREAM_IN_BULLETIN` default off really
   excludes world candidates; FR-016 import rule change in `test_world_storage.py` is narrow.
6. Day number (FR-006) and the full-report link.
7. CLI: dry run only, no writes, no model calls; exit codes.
8. Doc `builder.md` matches code, rules name tests; registrations; `check_code_docs.py --diff
   origin/master --strict` (exit code).
9. **Mutation checks**: at least 12 hand mutations (each cap, harm guard, headline guard, reaction
   limits, date variant, switch, threshold comparison, dedup key, skip reasons); table.
10. Run the new tests and `tests/unit/test_world_storage.py`, ruff on `src tests`.

## Report (final message)

Verdict (merge / merge after fixes / do not merge); findings by severity with file:line, the concrete
failure and a one-line fix; "must fix" separate from "nice to have"; anything that changes what
readers see listed separately; mutation table; checks run.
