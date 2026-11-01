# Prompt: review of PR #190 (018 world stream W6, text download) (2026-11-01)

You review PR #190 (`feat/018-world-w6-text`). You did not write it. **Read-only: no commits,
pushes, merges, PR comments, paid calls, network or production access.** Never run any command that
changes `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself (no `gh pr checkout`, no `git checkout`
there); you may read files there. Report in English.

## Read

- `gh pr view 190`, `gh pr diff 190`, `gh pr checks 190`.
- Implementer worktree (do not edit it): `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.claude/worktrees/agent-ae324b70864b53064`.
  For your runs and mutations, create a worktree of `origin/feat/018-world-w6-text` under your
  scratchpad named with `pr190`; never remove one you did not create; remove yours at the end.
- `AGENTS.md`; `src/app/core/archive/capture.md`; plan
  `specs/018-daily-inference/records/plan-item5-world-sources-2026-10-31.md` sections 5, 6.1 and
  6.2 step 6; the W6 prompt `records/prompt-item5-w6-2026-11-01.md` (on the PR branch).
- Implementer report (judge each decision):
  `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/coord-records/specs/018-daily-inference/records/report-item5-w6-2026-11-01.md`.

## Check

1. **Production archive job (most important).** The PR changes `capture.py` (`_download_step`
   `only=`) and `ArchiveRepo.due(..., ids=)`, which the nightly 03:00 archive job uses in
   production. Is the nightly behavior unchanged when `only`/`ids` are not given (same documents,
   order, budgets, outage rule, metrics)? Do world documents in the archive change the nightly job:
   its coverage numbers, its download budget and time (could 100 extra failed world documents eat
   the nightly budget on retries), archive size warning, retention? Propose the smallest fix if they
   do.
2. ER-9 and FR-016: no `articles` rows; archive text never reaches web/digest; import rules still
   hold; the transient `Article` is never added to a session.
3. Robots, bot agent, per-host pacing and outage rule really come from the archive code (not
   reimplemented); `test_world_text_goes_through_archive_robots_and_bot_agent` is not vacuous.
4. N bound: never more than `WORLD_TOP_N` pages per run, across reruns and `no_text` fallbacks to
   the next outlet; a cluster cannot loop forever over outlets.
5. State changes: `transition` keeping `last_error` for `no_text` (does it affect other moves or
   W3-W5 tests?); outage leaves `screened_in`; `no_text` never requeued; text seam cut to the Jev
   content limit; step B money rules unchanged.
6. `world texts --dry-run` writes nothing; not wired into the 04:00 job; no timer.
7. Docs (`world.md`, `capture.md`) match the code; every rule names tests or says none;
   `scripts/check_code_docs.py --diff origin/master --strict` (exit code).
8. Tests check behavior, not mocks. **Mutation checks**: at least 10 hand mutations (only/ids filter
   off, `due` ids ignored, N bound, outage -> `no_text`, robots outcome, error kept/cleared, seam cut,
   transient Article added to session, dry-run guard, ranking of no_text clusters); table killed /
   survived.
9. Run in your worktree:
   `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/pytest -q -o addopts="" tests/unit/test_world_text.py tests/unit/test_world_screen.py tests/unit/test_world_storage.py tests/unit/test_archive_capture.py | tail -3`,
   ruff on `src tests`, and any other archive test files you find relevant.

## Report (final message)

Verdict (merge / merge after fixes / do not merge); findings by severity with file:line, the concrete
failure and a one-line fix; "must fix" separate from "nice to have"; mutation table; checks run.
