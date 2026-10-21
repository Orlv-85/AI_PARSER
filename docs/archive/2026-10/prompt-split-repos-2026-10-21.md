# Prompt: split `storage/repos.py` by repository (2026-10-21)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first. Work in a separate git worktree from `origin/master`; other sessions may
work in the main folder. `venv1` is installed editable on the main folder: in the worktree run
checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/...` (adjust the relative path).

## Context

`docs/plan-split-overloaded-modules-2026-10-21.md` (merged in PR #64) is the reviewed plan; this is
its step 1. Read its "General rules" and section 1. `src/app/storage/repos.py` (1605 lines) holds six
unrelated repositories. Split it by moving code only: no behavior change.

## Target

- `storage/source_repo.py` - `SourceRepo`.
- `storage/article_repo.py` - `ArticleRepo`, `ArticleDailyStats`, `_publication_since`,
  `_publication_before`.
- `storage/source_candidate_repo.py` - `SourceImportBatchRepo`, `SourceCandidateRepo` (with the
  `TYPE_CHECKING` import of `CandidateOverlapGroup`).
- `storage/digest_repo.py` - `NewsDigestRepo`.
- `storage/repos.py` keeps `WeeklyAnalyticsRepo` and its dataclasses (weekly v2 decision is
  deferred; do not touch that code beyond the removed classes). If it needs a moved helper, import
  it from the new module.

## Rules

- Move code verbatim: no logic edits, no renamed classes or methods, no reformatting beyond imports.
  `git mv repos.py article_repo.py` for the largest part is fine if history then follows the bulk;
  say which file kept history.
- Update every importer of `app.storage.repos` in `src/`, `tests/`, `scripts/` to import from the new
  module. Check `src/app/storage/__init__.py` re-exports. No shims at the old path.
- Monkeypatch: grep tests for quoted `"app.storage.repos.` strings and for
  `setattr(<repos module>, ...)`; each patch must still hit the module where the code looks the name
  up. The plan lists one string (`SourceCandidateRepo.record_validation_result`); verify there are
  no others.
- Docs: update paths that name `storage/repos.py` in current docs (`src/app/core/ingestion/pipeline.md`
  Code map, `src/app/README.md`, `docs/`), not `specs/` or `docs/archive/`. Mark step 1 done in
  the plan file (one line).

## Checks

- Full gate: `make lint PYTHON=...`, full `pytest` (same pass count as `origin/master`),
  `scripts/check_code_docs.py` and `--diff origin/master --strict`.
- Smoke: `ai-news --help`, the web app factory, MCP server import, `--help` of each changed script.
- Package build like Docker: `pip wheel --no-deps` from a clean copy and check the new modules are in
  the wheel.

## Output

- One PR, do not merge. In your reply: the PR link; new module sizes in lines; importers changed by
  area; monkeypatch strings changed; exact checks with pass counts; open questions one line each
  (how settled, or a yes/no question for the owner with a recommendation, only if it changes what
  readers see or what is paid).
- Save any prompt you write for another session to a file per `AGENTS.md`.
