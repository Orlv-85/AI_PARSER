# Prompt: review of the spec 018 small fixes batch (2026-11-16)

You are a fresh, read-only reviewer. Do not edit, commit or push anything.

- Worktree: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-018-small-fixes` (branch
  `fix/018-small-batch`, uncommitted changes against `origin/master`). See them with
  `git -C <worktree> diff` and `git -C <worktree> status --short` (one new test file is untracked:
  `tests/unit/test_bulletin_told_before.py`).
- The task: `specs/018-daily-inference/records/prompt-small-fixes-batch-2026-11-16.md` (five fixes,
  their rules and tests). The implementer's report: `report-small-fixes-batch-2026-11-16.md` in the
  same folder. Rules of the repo: `AGENTS.md` (feature docs next to code, TDD, catch expected
  exceptions only, ASCII).
- `build/requirements.txt` (fastapi bump) is the owner's, not part of the review.

Check, for each fix:
1. Correctness: does the code do what the rule says, in every branch? Look for a case where it is
   wrong (e.g. fix 1: a headline when every shown story is removed, a builder headline, the
   reserve; fix 2: a candidate matched by both URL and title, a digest vs world candidate, an
   unreadable stored day; fix 3: an exception inside the writer body or at journal close, the
   summary and log fields; fix 5: a candidate in both `repeats` and a `same_event` group,
   non-Latin titles, the `kept` entries).
2. Tests: does each named test pin the rule (would it fail if the rule broke)? Any rule in the
   docs without a test, or a test that cannot fail?
3. Docs: do `writer.md`, `builder.md`, `repeats.md`, `daily.md` state the rules as they are now,
   short and dry, with the test names; any stale sentence left? Anything readers of stored
   `numbers` (web pages, CLI output) depend on that changed shape?
4. Run, from the worktree with `export PYTHONPATH=src` and `set -o pipefail`:
   `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q tests/unit/test_bulletin_*.py tests/unit/test_web_bulletin_page.py tests/unit/test_layer_imports.py tests/unit/test_monkeypatch_targets.py tests/unit/test_code_docs.py tests/unit/test_cli*.py`
   and report the last lines. Also `git grep -n "told_before\|\"kept\"\|numbers\[" -- src tests` to
   find other readers of the changed summaries.

Final message (you cannot write files): verdict (approve / fix needed), then findings, most severe
first, each with file:line, the concrete failing case and a suggested fix; then what you ran and
its output. Keep it under 60 lines.
