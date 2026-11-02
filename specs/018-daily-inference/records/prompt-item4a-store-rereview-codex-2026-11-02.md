# Prompt (Codex re-review, gpt-6-astra high): item 4a after fixes (2026-11-02)

Read-only. Same worktree: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4a-store`
(uncommitted; compare with `origin/master`, include untracked files). No edits, commit, push, gh,
network or paid calls.

Your first review: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/tasks/item4a-store.review-20261102-082246.md`.
The fix prompt: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/prompt-018-item4a-store-fixes-codex-2026-11-02.md`.

Check only:
1. Each of your findings and survivors is fixed, with a test that would fail without the fix.
2. The new code: `Candidate.article_id` / `Story.article_ids` (builder, loader), the refresh after
   a refused or successful save, the `bulletin_stored` log, the 503 test, the PostgreSQL
   integration test (would it actually run and pass in CI with `AINEWS_TEST_POSTGRES_URL`? any
   leftovers between tests, schema isolation?). Does the writer packet or any existing output
   change because of the new fields?
3. Docs match the code; named tests exist.
4. Run: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" tests/unit/test_bulletin_store.py tests/unit/test_bulletin_builder.py tests/unit/test_bulletin_writer.py | tail -1`

Report: findings most severe first (file:line, problem, failing input, one-line fix), then "clean"
if nothing must change before merge. Brief.
