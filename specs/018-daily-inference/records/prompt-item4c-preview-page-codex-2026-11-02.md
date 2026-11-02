# Prompt (Codex, gpt-6.1-sol high): spec 018 item 4c, hidden bulletin preview page (2026-11-02)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch
`feat/018-item4c-preview-page`, checked out from origin/master):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page`. Do not touch
any other directory. Do not run git commit, push or any gh command. No network, no paid calls. Do
not spawn a doc review or any sub-agent: a separate reviewer (another model) reviews the code and
the doc after you.

Speed rule: while working run only the feature's tests and `ruff` on changed files; at the end run
the full suite, `make lint`, crapper, dryer and mutator once each, in that order; after a fix rerun
only the check that failed.

## Scope

Item 4 of spec 018: 4a (merged: table `bulletins`, `BulletinRepo`, `GET /api/news/bulletin`), 4b
(merged: `ai-news bulletin daily`, job, switches); 4c (this one): the hidden preview page of FR-019.
Spec: `specs/018-daily-inference/spec.md` FR-019 and User Story 2. Item 6 (later, separate design
session) makes the real home page; 4c is a plain, correct page for checking real days, not a design.

## Decisions already made (put them in the doc's Decisions as "decided 2026-11-02 (agent)")

- `GET /bulletin?date=YYYY-MM-DD`, public (add `/bulletin` to the unprotected paths in
  `src/app/web/app.py`, like `/weekly`), not linked from any page or script of the site, and
  `<meta name="robots" content="noindex, nofollow">`. `/` and every other page stay unchanged.
  The settings `bulletin_home_page` / `bulletin_post_channels` are not read in 4c.
- Server-rendered from the stored row through `BulletinRepo` (no request to the JSON API, no
  model call), the same way the existing pages are filled (`src/app/web/routes/pages.py`, template
  in `src/app/web/`, HTML parts in a view module like `src/app/web/signals_view.py`). New view
  module `src/app/web/bulletin_view.py`; template `src/app/web/bulletin.html`; reuse an existing
  public stylesheet if one fits, else one small file under `src/app/web/static/` (not under
  `static/admin/`). Page language as the existing public pages.
- Without `date`: the latest ready day (as the API). With `date`: that day.
- Ready day: header with the date (and day number), then the stories in stored order. Per story:
  `headline` when the writer set it, else `title`; `site_note` paragraphs when present; `gloss` when
  present; area; outlet names as links from `links`; a small mark of `text_origin` (title / model)
  and `origin` (digest / world) for checking. Also show the stored `numbers` (assessed,
  digest_articles, writer summary) in a small block at the bottom, for checking.
- Skipped day: says no bulletin for this day with the stored reason, and links to the digest of
  that day `/?date=D` (the digest moves to `/daily` only in item 6).
- No row for the date: HTTP 404 page with the same text and digest link. Malformed date: 400.
  Storage failure: 503 page. No ready day at all and no date: 404 page saying nothing is stored yet.
- Previous / next day links (`/bulletin?date=D-1`, `D+1`; no next link past yesterday UTC).
- Security: every stored text is escaped (`html.escape`); a link is rendered only for `http`/`https`
  URLs, others as plain text. Stored text comes from models and outlets.

## Steps (doc first, then failing tests, then code)

1. Read `AGENTS.md`, `src/app/web/pages.md`, `src/app/storage/bulletin_store.md`,
   `src/app/core/bulletin/builder.md` (Story fields), `src/app/core/bulletin/writer.md` (headline,
   site_note, gloss, text_origin), `src/app/web/app.py`, `src/app/web/routes/pages.py`,
   `src/app/web/routes/bulletin.py`, `src/app/web/signals_view.py`, and their tests
   (`rg -l "build_pages_router|test_api_bulletin|route_table" tests`).
2. Doc: add the preview page to `src/app/web/pages.md` (it covers `pages.py` and the templates):
   Behavior rules with test names, Decisions above, Invariants (no link to `/bulletin` anywhere on
   the site; `/` unchanged; no model call), Code map rows. Add `src/app/web/bulletin_view.py` to its
   `covers:`. If the route lives outside `pages.py`, cover that file too. Register nothing new
   unless you create a new doc (prefer not to).
3. Failing tests first (run them, see each fail for the expected reason), at least:
   - `test_bulletin_page_shows_ready_day` (headline over title, site_note, outlet links, marks)
   - `test_bulletin_page_title_only_day` (no writer fields: title shown)
   - `test_bulletin_page_defaults_to_latest_ready`
   - `test_bulletin_page_skipped_day_links_digest`
   - `test_bulletin_page_missing_day_is_404`, `test_bulletin_page_bad_date_is_400`,
     `test_bulletin_page_storage_failure_is_503`, `test_bulletin_page_empty_store_is_404`
   - `test_bulletin_page_escapes_stored_text` (`<script>` in headline and outlet; `javascript:` url)
   - `test_bulletin_page_is_public_and_noindex` (auth enabled, no session: 200; robots meta)
   - `test_bulletin_page_is_not_linked` (no template, view module or static file other than the
     page itself contains `/bulletin`)
   - `test_bulletin_page_prev_next_links` (no next link for yesterday UTC)
   - update the pinned route table test for the one new route; existing `/` tests stay unchanged.
4. Code, smallest change in the current style; functions small (complexity under 10).
5. Final checks (once each, in this order; report last lines and exit codes):
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" -n auto | tail -1`
   - `PYTHONPATH=src make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python 2>&1 | tail -5`
   - `env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 ~/tools/unclebob/crapper/crapper src/app/web/bulletin_view.py src/app/web/routes/pages.py src/app/web/app.py`
     (report functions you wrote or changed with CRAP >= 10)
   - `~/tools/unclebob/dryer/dryer --threshold 0.8 src/app/web/bulletin_view.py src/app/web/signals_view.py src/app/web/routes/pages.py`
     (report pairs that involve code you wrote)
   - `env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 ~/tools/unclebob/mutator/mutator --use-existing-coverage --test-command "/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= <your page test file>" src/app/web/bulletin_view.py`
     (kill survivors with tests or give a one-line reason)
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python scripts/check_code_docs.py --diff origin/master --strict; echo exit=$?` (alone, last)

## Report (your final message)

Files changed, one line each; failing-test output of step 3; outputs of step 5; mutator sites,
killed, survived, uncovered and what you did with survivors; anything you decided yourself or
could not do, one line each.
