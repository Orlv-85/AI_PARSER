# Prompt: feature doc for source onboarding, before its split (2026-10-21)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first, especially "Feature Docs Next To Code". Work in a separate git worktree
from `origin/master`; other sessions may work in the main folder. `venv1` is installed editable on
the main folder: in the worktree run checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/...`.

## Context

Source onboarding (admin imports candidate sources, the app classifies, validates and groups them,
the operator approves or rejects, approved sources join collection) has no code doc. Its main
module `src/app/core/sources/onboarding.py` (1005 lines) will be split next (section 2 of
`docs/plan-split-overloaded-modules-2026-10-21.md`), and `SourceOnboardingService` will move out
of `src/app/web/service.py`. AGENTS.md: an older feature gets its doc when it is next changed, and
the doc comes before the code. This task writes the doc only; a different session reviews it,
then another one splits the code.

## Write `src/app/core/sources/onboarding.md`

Use `src/app/core/ingestion/pipeline.md` and `src/app/core/daily/signals.md` as the reference
format (header, Behavior with a Mermaid flow, Decisions, Invariants, Code map, Tests).

- Header `covers:` at least `src/app/core/sources/*.py`, `src/app/storage/source_candidate_repo.py`,
  `src/app/web/routes/sources.py`, `src/app/web/source_intake.py`, `scripts/sources_onboarding_helper.py`
  if the checker accepts scripts (read `scripts/check_code_docs.py`); `SourceOnboardingService` in
  `web/service.py` is named in the Code map (the file is shared, do not cover it).
- Behavior: what happens to a candidate from import to an enabled source (limits by constant name:
  batch size, file size, overlap rules, validation of RSS and HTML candidates, review actions,
  YAML export, how an approved candidate becomes a DB-managed source that `run_fetch_cycle`
  fetches - link to the pipeline doc rule, do not repeat it). Every rule names the tests that
  check it, verified against the test code; a rule without a test says "no test".
- Decisions: decision and why, one or two lines; search the history first (`specs/` for source
  onboarding, `docs/archive/`, `git log -S`, PR descriptions). A reason no source states is written
  "decided 2026-10-21 (agent): <reason>", and you list it in your reply.
- Code map: today's functions and which of the three planned modules (`candidates.py`,
  `validation.py`, `onboarding.py`) each goes to after the split; the patch targets the plan lists.
- Register the doc in `docs/README.md`, `README.md`, `src/app/README.md`; the main module's
  docstring names it (the only code change).

## Checks

- `scripts/check_code_docs.py` and `--diff origin/master --strict` after the commit; ruff on the
  docstring change. Docs and a docstring only: the full gate is not needed; say so in the PR.

## Output

- One PR, do not merge. In your reply: the PR link; rules without a test (list); decisions marked
  "decided (agent)" (list); doubtful or dead code found (file:line), not changed; questions for the
  owner only if they change what readers see or what is paid (yes/no with a recommendation).
- Save any prompt you write for another session to a file per `AGENTS.md`.
