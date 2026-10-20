# Prompt: answer the "why: unknown" decisions of the fetch pipeline (2026-10-20)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first. Work in a separate git worktree from `origin/master`; other sessions may
work in the main folder.

## Context

`src/app/core/pipeline.md` (merged in PR #54) is the feature doc of news ingestion: the intended
current behavior, written before a refactoring. Its Decisions table has 8 rows with "why: unknown".
The owner does not take part in this project beyond a minimum: you answer these questions
instead of the owner. You are a different model from the one that wrote the doc; read it critically.

## The 8 questions

1. Conditional fetch of HTML list pages is off by default (`fetch_conditional_html_list_enabled`).
2. The canonical URL hash is the only article identity; simhash and aliases planned in 001 FR-4 were
   never wired in (two URLs of one story are two articles).
3. The weights of `rank_score` and the half-life of `freshness_score`.
4. Scores are computed once at ingestion; freshness of stored rows never decays.
5. With admission on, a screening outage pauses collection; there is no keyword fallback.
6. With admission off, a Jev failure falls back to keywords and stops Jev calls for the cycle.
7. RSS full text is off in `scripts/auto_update_once.sh` and on in `scripts/run_daily_fetch_job.sh`.
8. The weekly report trigger runs inside the fetch cycle.

## Method, per question

1. Look for evidence: `git log -S` / `git log -p` on the relevant lines and settings, commit
   messages, PR descriptions (`gh pr list --state merged --search ...`, `gh pr view N`),
   `specs/001-*`, `specs/002-*`, `specs/011-*`, `specs/*/records/`, `docs/archive/`,
   `docs/configuration.md`, `docs/deploy.md`, deploy files. Production values may differ from code
   defaults: check `docker-compose.prod.yml`, `deploy/`, `.github/workflows/deploy-*.yml`
   (read only, never change them).
2. Classify the answer:
   - **found** - a source states the reason: write it, cite the source (commit hash, PR number or file).
   - **decided** - no source: judge on technical merits (cost, correctness, simplicity, current
     production behavior) and write "decided 2026-10-20 (agent): <reason>". Do not present a guess
     as history.
   - **change proposed** - the current behavior looks wrong or not worth keeping: keep the row as it
     is in the code, add the proposal to your report (not to the doc), with the risk.
   - **owner** - only if the answer changes what readers see or what is paid, and the evidence does
     not settle it. Expect at most one or two; give the owner a one-line yes/no question with your
     recommendation.
3. Question 8 touches weekly analytics: the keep-or-delete decision on weekly v2 is deferred until
   weekly work starts. Answer only "found" or "decided", propose no change.

## Output

- One PR that edits only the 8 rows of the Decisions table in `src/app/core/pipeline.md`
  (ASCII, one or two lines per row, same style as the other rows). No code changes, no other rows.
- Checks: `./venv1/bin/python scripts/check_code_docs.py`, and `--diff origin/master --strict` after
  the commit. The full gate is not needed for a docs-only change; say so in the PR.
- Note: `venv1` is installed editable on the main folder; in a worktree run checks with
  `PYTHONPATH=src`.
- Do not merge. In your reply: the PR link, a table "question | class | answer in one line", the
  "change proposed" items with risks, and the "owner" questions (if any) as yes/no lines.
- Save any prompt you write for another session to a file per `AGENTS.md`.
