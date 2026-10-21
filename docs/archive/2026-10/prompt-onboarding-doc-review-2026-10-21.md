# Prompt: review the source onboarding feature doc, PR #75 (2026-10-21)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first, especially "Feature Docs Next To Code" and "Owner And Questions". Other
sessions may work in the main folder: check out the PR branch `docs/onboarding-doc-20261021` in a
separate git worktree. `venv1` is installed on the main folder: in the worktree run checks with
`PYTHONPATH=src ../AI_PARSER/venv1/bin/...`.

## Context

PR #75 (https://github.com/Orlv-85/AI_PARSER/pull/75) adds `src/app/core/sources/onboarding.md`,
the feature doc of source onboarding, written before `core/sources/onboarding.py` is split
(section 2 of `docs/plan-split-overloaded-modules-2026-10-21.md`). AGENTS.md: a doc is drafted by
one session and reviewed by a different one. You are the reviewer. Format reference:
`src/app/core/ingestion/pipeline.md`.

## Check

1. Behavior: every rule against the code (`core/sources/onboarding.py`, `core/sources/review.py`,
   `web/source_intake.py`, `web/routes/sources.py`, `web/service.py` `SourceOnboardingService`,
   `storage/source_candidate_repo.py`, `storage/source_repo.py`). Every named test must really
   check the rule (read the test body, not only its name). Rules marked "no test" must really
   have none. Look for behavior the doc misses.
2. Decisions: each "why" against its cited source (`specs/003-source-onboarding-management/`,
   `specs/011-json-source-intake/`, PR #8 body via `gh pr view 8`). The two
   "decided 2026-10-21 (agent)" entries: is the reason sound?
3. Code map: the planned split table (every function of `onboarding.py` placed once, no import
   cycle), and the patch-target table against `tests/` (`grep -rn "monkeypatch.setattr" tests`,
   quoted `app.core.sources.onboarding.*` strings, `hasattr(source_onboarding, ...)`).
4. Format: short and dry, rules not numbers, no history; header `covers:` sensible.
5. `python3 scripts/check_code_docs.py` and `--diff origin/master --strict`.

## Output

- Fix clear errors in the doc yourself on the PR branch (one commit, push, do not merge).
- Save the review to `docs/review-onboarding-doc-2026-10-21.md` (findings: file:line, what is
  wrong, fixed or not) and post a short summary as a PR comment.
- In your reply: the commit, findings not fixed, and questions for the owner only if they change
  what readers see or what is paid (yes/no with a recommendation); everything else decide and report.
- Save any prompt you write for another session to a file per `AGENTS.md`.
