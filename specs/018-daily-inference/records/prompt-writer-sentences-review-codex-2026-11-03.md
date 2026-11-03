# Prompt (Codex review, gpt-6-astra high): spec 018 writer, paragraph split (2026-11-03)

Read-only review. Directory (git worktree of branch `fix/018-writer-sentences`, changes uncommitted;
compare with `origin/master`): `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/writer-sentences`.
Do not edit files, commit, push or use gh. No network, no paid calls. Do not spawn a sub-agent.

The executor's prompt (problem, decisions, tests):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/prompt-018-writer-sentences-codex-2026-11-03.md`.

## Check

1. `git diff origin/master` in full.
2. `split_sentences` with concrete inputs: decimals and thousands, currency, percent, `U.S.`, `U.K.`,
   initials, listed abbreviations, a sentence that really ends with a single capital letter or an
   abbreviation (`... Plan B. Next`, `... at Acme Inc. The ...`): what happens, and is the loss
   acceptable (a merged sentence is still checked; a wrong split could drop a fragment)? Closing
   quotes and parentheses, curly quotes, `?`/`!`, ellipsis `...`, URLs or e-mail addresses, lowercase
   start after a period, empty or whitespace-only items, non-string items (schema path).
3. `_sentences`: cap after split, `over_limit` count, drop codes numbered after split, grounding
   and word-count checks per sentence, fallbacks unchanged (title when nothing passes).
4. Prompt and `WRITER_VERSION`: wording matches the decisions; version bump pinned by the test;
   anything else in the prompt changed by accident? Journal effect of the new version (new request
   body -> a new paid call only for a new run; caps unchanged).
5. Doc `writer.md`: rules match code, tests named exist and check them, decisions dated.
6. Tests: would they fail if the split were removed? Hand mutations (no split; cap before split;
   numbering per item; drop the abbreviation guard; split on `.` without whitespace) and which tests
   kill them. Use `PYTHONDONTWRITEBYTECODE=1`.
7. Run: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" tests/unit/test_bulletin_writer.py tests/unit/test_bulletin_daily.py | tail -1`

## Report (your final message)

Findings ranked most severe first: file:line, problem, concrete failing input, one-line fix. Then
mutation results. Then "clean" if nothing must change before merge. Be brief.
