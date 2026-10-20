# Prompt: two small behavior fixes - close the RSS/HTML-list Fetcher, admin list sorted by date (2026-10-20)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first. Work in a separate git worktree from `origin/master`; other sessions may
work in the main folder (a parallel session is adding pipeline tests, see
`docs/prompt-pipeline-tests-2026-10-20.md`; if its PR is merged before yours, rebase on it).
`venv1` is installed editable on the main folder: in the worktree run checks with
`PYTHONPATH=src ../AI_PARSER/venv1/bin/...` (adjust the relative path).

The owner approved both changes on 2026-10-20. Keep the PR to exactly these two.

## 1. Close the Fetcher of a source fetch

`src/app/core/pipeline.py`, `_fetch_source_items` (around line 596) creates a `Fetcher` (pooled
`httpx` client) and never closes it: every source fetch leaks its client. The HTML article stage
(`_process_html_links_two_stage`, around line 998) closes its own in `finally`, but creates it before
the `try` (the admission placeholder loop runs between them), so an error there leaks too.

- Close both on every path (`with Fetcher(...) as fetcher:` or `try/finally`); `Fetcher` already
  has `close`, `__enter__`, `__exit__` (`src/app/ingest/fetcher.py`).
- Behavior must stay the same otherwise: same requests, same results, same fakes in tests still
  work (many tests replace fetch functions in `core/pipeline.py`; keep them meaningful).
- Tests: the Fetcher of a source fetch is closed after success and after a fetch error; the HTML
  stage Fetcher is closed when the placeholder loop raises. Use a fake/spy `Fetcher`, no network.

## 2. Admin news list: default sort by date

The admin page (`/admin`, `src/app/web/index.html`, the `#sort` select) defaults to `rank`. Make
`published` the default selection of the admin page. Do **not** change the default of the
`/api/news` or `/api/news/export` `sort` query parameter (API backward compatibility,
`AGENTS.md`); the page sends `sort` explicitly. Keep the other options.

- Check what else reads the select (export link, saved state) and that it follows.
- Test: the rendered admin page has `published` selected by default (follow how existing tests of
  `index.html` / `_render_index` check the page).

## Doc first

`src/app/core/pipeline.md` is the feature doc (edit it before the code):
- HTTP rule: say the `Fetcher` is closed after the source fetch and after the HTML article stage;
  add the new test names.
- Decisions row "`rank_score` is a legacy sort key...": it lists "the admin list sort" among the
  readers of rank; update it (the admin list now defaults to publication date, rank stays an
  option and the API default).
The admin page has no code doc; do not create one.

## Checks

- `PYTHONPATH=src .../venv1/bin/python scripts/check_code_docs.py`, and after the commit
  `--diff origin/master --strict`.
- Full gate before the push: `make lint PYTHON=...`, full `pytest`.

## Output

- One PR, do not merge. In your reply: the PR link, what changed (file:line), tests added, exact
  checks run and their result, and any open question one line each (how settled, or a yes/no
  question for the owner with a recommendation, only if it changes what readers see or what is paid).
- Save any prompt you write for another session to a file per `AGENTS.md`.
