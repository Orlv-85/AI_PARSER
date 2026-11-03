# Prompt (Codex review, gpt-6.1-sol high, fresh session): ub-mode pass 3, daily enrichment (2026-11-03)

Read-only review. Directory (git worktree of branch `refactor/ub-enrichment`, changes uncommitted;
compare with its base `git merge-base HEAD origin/master`, include untracked files):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/ub-enrichment`.
Do not edit files, commit, push or use gh. No network, no paid calls. Do not spawn a sub-agent.
For hand mutations copy `src` to a temp directory and run tests with `PYTHONPATH` pointing there
first and `PYTHONDONTWRITEBYTECODE=1`, or reason statically; say which.

The executor's prompt: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/prompt-ub-pass-enrichment-codex-2026-11-03.md`;
its report: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/tasks/ub-enrichment.exec-*.md` (newest).
A pure refactor of the nightly paid digest enrichment (Jev and DeepSeek calls through the payment
journal) plus characterization tests. Any behavior change is a defect.

## Check

1. The diff in full (`src/app/core/daily/enrichment.py`, `provider_requests.py`, the doc, tests,
   `docs/troubleshooting.md`, and any file under `docs/work/` the executor added in the worktree).
2. Equivalence, function by function, old vs new (`enrich`, `reusable`, `grounded_summary`,
   `publish_day`, `source_row`, `parse_review`, `parse_jev` and every new helper): same results,
   exceptions and messages, log events and fields, SQL, journal calls and their order (reservation
   before dispatch, one call per request key), caps, cache keys, order of checks where the first
   failing check names a reason, short-circuit evaluation (a paid call that the old code skipped
   must still be skipped). Name any difference with a concrete input.
3. Doc `src/app/core/daily/enrichment.md`: rules match code, every named test exists and checks its
   rule, `covers:` right.
4. Tests: real assertions on returned rows, journal rows/states, call order, log fields? Hand
   mutations (skip a reuse check so a paid call repeats; reorder two admission checks; drop a cap
   check; change a cache key field; make `parse_jev` accept a lower confidence) and which tests kill
   them; name survivors.
5. Run: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" tests/unit/test_daily_enrichment.py tests/unit/test_daily_publish_day.py tests/unit/test_provider_requests.py tests/unit/test_provider_requests_parse.py tests/unit/test_cli_daily_publish.py tests/unit/test_monkeypatch_targets.py | tail -1`

## Report (your final message)

Findings ranked most severe first: file:line, problem, concrete failing input, one-line fix. Then
mutation results. Then "clean" if nothing must change before merge. Be brief.
