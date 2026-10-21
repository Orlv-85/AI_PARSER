# Prompt: remove the finished one-off cleanup tools (2026-10-21)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first. Work in a separate git worktree from `origin/master`; other sessions may
work in the main folder (a parallel session may be splitting `web/app.py`; it does not touch these
files; if its PR merges first, rebase). `venv1` is installed editable on the main folder: in the
worktree run checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/...` (adjust the relative path).

## Context

`docs/plan-storage-layout-2026-10-21.md` (PR #70) lists two finished one-off operations:

- legacy article cleanup with Jev (run 2026-10-11): `storage/legacy_cleanup.py`,
  `storage/cleanup_journal.py`, `core/ingestion/legacy_cleanup.py`,
  `scripts/legacy_articles_cleanup.py`, operator guide `docs/legacy-articles-jev-cleanup.md`;
- non-news cleanup plan (2026-10-10): `storage/non_news_cleanup.py`, `scripts/non_news_cleanup.py`.

Remove them if nothing live depends on them. Production behavior (collection, digest, signals,
site) must not change.

## Find out first (report the evidence)

- Every importer of these modules in `src/`, `scripts/`, `tests/`. Known live users to check:
  `core/daily/reenrich_pilot.py` imports `CLEANUP_POLICY`, `cleanup_verdict` from
  `core/ingestion/legacy_cleanup.py`; `scripts/reenrich_articles.py` imports from
  `storage/legacy_cleanup.py`; `legacy_cleanup.py` imports `EXPORT_TABLES`, `_reference_ids` from
  `non_news_cleanup.py`. Decide for each whether the user is live (scheduled job, CLI command,
  web, an operator guide still in `docs/` that is not a finished record) or finished itself.
- Whether anything scheduled or deployed runs the scripts (`scripts/*.sh`, `deploy/`, systemd
  timers in `scripts/install_daily_timers.sh`, workflows, `docs/deploy.md`).
- `known_article_fk` / `DERIVED_CASCADE_TABLES`: this guard only protects a destructive cleanup
  from deleting articles that new tables reference. If the cleanup goes, say whether the guard is
  still needed anywhere (for example by `ArticleRepo.prune_older_than` or the non-news delete path);
  if yes, move it next to that code with its test; if no, remove it.

## Change

- Delete what is finished; keep what a live user needs, moved to a module named for what it does
  (no `legacy_` name for live code), code verbatim, imports updated, no shims.
- Delete the tests of deleted code only; keep the rest.
- Docs: remove or archive the operator guide of a deleted tool (`docs/archive/2026-10/`, add a line
  that the code was removed in this PR and how to restore it from git); update
  `docs/README.md`, `README.md`, `src/app/README.md`, `docs/plan-storage-layout-2026-10-21.md`
  (one line: done). Not `specs/`.
- Weekly v2 files: only imports, if any.

## Checks

- Full gate: `make lint PYTHON=...`, full `pytest` (report the pass count and the removed tests),
  `scripts/check_code_docs.py` and `--diff origin/master --strict`.
- Smoke: `ai-news --help`, the web app factory, `--help` of each remaining changed script.

## Output

- One PR, do not merge. In your reply: the PR link; what was deleted and what was kept (with the
  live user that keeps it); lines removed; the `known_article_fk` verdict; exact checks with pass
  counts; open questions one line each (how settled, or a yes/no question for the owner with a
  recommendation, only if it changes what readers see or what is paid).
- Save any prompt you write for another session to a file per `AGENTS.md`.
