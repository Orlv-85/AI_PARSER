# Prompt: review of PR #155, spec 018 item 1 (2026-10-31)

You review PR #155 (`feat/018-world-change`) of `ai-news-collector`
(https://github.com/Orlv-85/AI_PARSER/pull/155). You did not write it. **Read-only: no commits, no
pushes, no merges, no PR comments, no paid calls, no production.** Report in English.

## Read

- `gh pr diff 155` and `gh pr view 155`; `gh pr checks 155`.
- The spec on `origin/master`: `git show origin/master:specs/018-daily-inference/spec.md` (FR-001,
  FR-002, FR-003, FR-012, Key Entities, item 1) and `AGENTS.md` (Feature Docs Next To Code, Code
  Changes, Validation).
- Context in the PR's worktree
  `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.claude/worktrees/agent-a1a702c7a0f95c6ee`:
  `src/app/core/jev.py`, `src/app/core/daily/rubric.py`, `src/app/storage/provider_journal.py`,
  `src/app/core/daily/enrichment.py` (day scope), an existing migration as a pattern.

## Check

1. Correctness: the request body (model, state, exactly the four questions), the state text matches
   what the daily enrichment sends, answer parsing and validation, failure handling (never raises
   into callers), journal use and caps, idempotency per version, day scope equals the digest's.
2. Safety of existing behavior: `rubric.py` / `RUBRIC_VERSION` untouched; ingestion and daily
   enrichment unchanged; migration creates only when missing, downgrade drops, head id chain
   correct; no job wiring.
3. Doc `src/app/core/bulletin/world_change.md`: matches the code, every rule names its tests, the
   header and registrations are right.
4. Tests: do they test the claims, or only the mocks? Missing cases.
5. Run in that worktree: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/pytest -q -o addopts="" tests/unit/test_world_change.py tests/unit/test_period_signals_migration.py | tail -3`
   and `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python -m ruff check src tests`.

## Report (final message)

Verdict: merge / merge after fixes / do not merge. Findings ranked by severity, each with file:line,
the concrete failure, and the fix in one line. Separate "must fix" from "nice to have". Say exactly
which checks you ran.
