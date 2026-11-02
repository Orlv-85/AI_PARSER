# Prompt (Codex, gpt-6.1-sol high): world_change request fits the Jev byte bound (2026-11-02)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch
`fix/018-world-change-fit`, already checked out from origin/master):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/world-change-fit`. Do not touch any
other directory. Do not run git commit, push or any gh command: the coordinator commits and opens the
PR. No network, no paid calls.

## Why

First world night (2026-11-02, record `specs/018-daily-inference/records/world-days-2026-11-01.md`):
step B logged `world_change_failed` with `JevInputTooLarge` for 2 of 74 articles. Cause:
`world_change_state` bounds text by characters (`jev_state`: `CONTENT_LIMIT` 16000), while
`reservation` in `src/app/core/daily/provider_requests.py` bounds the encoded request by bytes
(`len(encoded(body).encode("utf-8")) + 2048 > 32000` raises), and `encoded`
(`src/app/storage/journal_files.py`) uses `ensure_ascii=True`, so each non-ASCII character costs 6
bytes. Long non-English texts never get assessed. The world stream is multilingual.

Wanted: a world_change request that would exceed the bound is sent with its content cut to the
longest prefix that fits. A request that already fits is sent exactly as today (same body, so the
same journal request key). Also: the failure log does not say which article failed.

## Steps (in this order; repo rule: doc first, then failing tests, then code)

1. Read `AGENTS.md`, `src/app/core/bulletin/world_change.md`, `src/app/core/bulletin/world_change.py`,
   `src/app/core/jev.py` (`jev_state`, limits), `src/app/core/daily/provider_requests.py`
   (`reservation`), `src/app/storage/journal_files.py` (`encoded`), `src/app/core/world_screen.py`
   (`_assess`), `tests/unit/test_world_change.py`.
2. Edit `src/app/core/bulletin/world_change.md`, section Behavior, part Request: add two rules, each
   with its test names:
   - "A request whose encoded size would exceed the Jev request bound (`JEV_REQUEST_BYTE_BOUND`,
     checked by `jev_request_fits`) is sent with the content cut to the longest prefix that fits; a
     request that fits is sent unchanged. Tests: `test_long_non_ascii_state_is_cut_to_fit`,
     `test_fitting_state_is_unchanged`, `test_request_fits_matches_reservation`."
   - "A failure or stop log line carries the article id when the object has one. Tests:
     `test_failure_log_names_the_article`."
   Section Decisions, one line: "Cut, not skip, an oversized text: decided 2026-11-02 (agent): the
   world stream is multilingual and the start of an article carries the news." Update the Code map
   and Tests sections if they list functions or tests. Lines at most 100 characters.
3. In `src/app/core/daily/provider_requests.py` plan (do not write yet) two names:
   `JEV_REQUEST_BYTE_BOUND = 32000` and `jev_request_fits(body: dict[str, Any]) -> bool` (True when
   `len(encoded(body).encode("utf-8")) + 2048 <= JEV_REQUEST_BYTE_BOUND`); `reservation` will use it
   with no change in behavior.
4. Write the failing tests in `tests/unit/test_world_change.py`:
   - `test_long_non_ascii_state_is_cut_to_fit`: an article with an ASCII title and content of 16000
     Cyrillic characters (e.g. "ж" repeated, or a short Russian sentence repeated); the assessor's
     `body(article)` passes `jev_request_fits`; its state begins with `world_change_state` of the
     same article up to the cut (the content in the body is a prefix of the original content);
     and the prefix is the longest: one more character would not fit.
   - `test_fitting_state_is_unchanged`: an ASCII article that fits: `body(article)["state"] ==
     world_change_state(article)`.
   - `test_request_fits_matches_reservation`: for a body just inside and just outside the bound,
     `jev_request_fits` is True / False and `reservation("jev", body)` returns / raises
     `JevInputTooLarge` accordingly.
   - `test_failure_log_names_the_article`: an assessor with a fake client that raises
     `httpx.HTTPError` (or returns a bad answer) and a recording logger; after `assess(article)` with
     `article.id == 7` the `world_change_failed` fields include `"article_id": 7`. Follow how the
     existing tests in this file build fakes and loggers.
   Run them and see them fail for the expected reason (import error or assertion):
   `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" tests/unit/test_world_change.py | tail -5`
5. Code, smallest change in the current style:
   - `provider_requests.py`: add `JEV_REQUEST_BYTE_BOUND` and `jev_request_fits`; `reservation`
     uses `jev_request_fits` for the jev branch (same error, same message).
   - `jev.py`: `jev_state` gets an optional keyword `content_limit: int = CONTENT_LIMIT`; default
     behavior unchanged.
   - `world_change.py`: `world_change_state(article, *, content_limit=CONTENT_LIMIT)` passes it on;
     `WorldChangeAssessor.body` builds the body as today; if it does not fit, find the largest
     `content_limit` in `[0, CONTENT_LIMIT]` whose body fits by binary search (deterministic, so the
     same article always gives the same body) and use that body. If even `content_limit=0` does not
     fit, return the uncut body (the journal raises as today and the failure is logged).
   - `ask` gets an optional `context: dict[str, object] | None = None` merged into the failed and
     stopped log fields; `assess` passes `{"article_id": article.id}` when the object has a non-None
     `id`. If importing `provider_requests` from `world_change.py` makes an import cycle, import it
     lazily inside the function, as `ask` already does for the journal module.
   - Do not change `WORLD_CHANGE_VERSION`, the questions, `world_screen.py` behavior or daily
     enrichment.
6. Run, from the worktree, and fix anything that fails:
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" tests/unit/test_world_change.py tests/unit/test_world_screen.py tests/unit/test_world_report.py | tail -1`
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" -n auto | tail -1`
   - `PYTHONPATH=src make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python 2>&1 | tail -5`
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python scripts/check_code_docs.py --diff origin/master --strict; echo exit=$?`
     (run it alone, last; if it names a doc for a changed covered file, update that doc's rule or
     Code map, then rerun).
   - `~/tools/unclebob/crapper/crapper --no-coverage src/app/core/bulletin/world_change.py src/app/core/daily/provider_requests.py`
     (report any function you changed with complexity above 10).

## Report (your final message)

Files changed with a one-line summary each; the failing-test output of step 4; the outputs of step 6
(last lines and exit codes); anything you could not do or decided yourself, one line each.
