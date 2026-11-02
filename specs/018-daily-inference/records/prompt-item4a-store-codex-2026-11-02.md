# Prompt (Codex, gpt-6.1-sol high): spec 018 item 4a, bulletin storage and API (2026-11-02)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch
`feat/018-item4a-bulletin-store`, already checked out from origin/master):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4a-store`. Do not touch any
other directory. Do not run git commit, push or any gh command: the coordinator commits and opens
the PR. No network, no paid calls (tests use fakes; never call Jev or DeepSeek).

## Scope

Item 4 of spec 018 is split in three PRs: 4a (this one) storage + CLI store + public API
(FR-007, FR-008); 4b daily job and switches (FR-019, FR-020); 4c hidden preview page. Do only 4a.

FR-007: a bulletin row per day: date, status (`ready`, `skipped`), payload (headline, sections,
stories with texts, areas, links, outlets, article ids, origin `model` or `title`), numbers,
versions, generated time, Telegram message id. Idempotent.
FR-008: public `GET /api/news/bulletin?date=` returns the stored bulletin; existing APIs unchanged.

## Decisions already made (do not reopen; put them in the doc's Decisions as "decided 2026-11-02 (agent)")

- Table `bulletins`: `day` (date, primary key), `status` (`ready` | `skipped`), `reason` (skip
  reason or null), `payload` (JSON: `Bulletin.as_dict()` for ready, `{}` for skipped), `numbers`
  (JSON: `assessed`, `digest_articles`, and the writer summary incl. `cost_usd` when the writer ran),
  `versions` (JSON: `bulletin` = new constant `BULLETIN_STORE_VERSION = "bulletin-store-1"`,
  `world_change` = `WORLD_CHANGE_VERSION`, `writer` = `WRITER_VERSION` when the writer ran),
  `generated_at` (UTC timestamp), `telegram_message_id` (bigint, null).
- Idempotent: saving a day replaces its row (upsert by `day`), except a row with a non-null
  `telegram_message_id` is never replaced (the save is refused and logged; the CLI exits 0). This
  keeps a posted bulletin equal to what was posted.
- A skipped day is stored too (status `skipped`, reason), so the job and the page can tell "no
  bulletin because ..." from "not built yet".
- The API returns the stored row as JSON (`day`, `status`, `reason`, `payload`, `numbers`,
  `versions`, `generated_at`; not `telegram_message_id`). With `date` absent: the latest `ready`
  day. 404 when nothing matches. 400 on a bad date. Public, like `/api/news/daily-signals` (see
  `src/app/web/app.py`, the public path set near line 98).

## Steps (in this order; repo rule: doc first, then failing tests, then code)

1. Read `AGENTS.md`; `src/app/core/bulletin/builder.md` and `writer.md`; `src/app/core/bulletin/builder.py`
   (`Bulletin`, `as_dict`); `src/app/cli/main.py` (`bulletin build`, lines ~495-555);
   `src/app/storage/models_sql.py`; `src/app/storage/world_change.py` and its migration
   `src/app/storage/migrations/versions/b8e2d4f61a07_add_world_change_assessments.py` (the pattern
   for a repo and a "create only when missing" migration); `src/app/web/routes/signals.py` and
   `src/app/web/app.py` (route and public-path pattern); `tests/unit/test_world_change.py`
   (migration round-trip test pattern), `tests/unit/test_bulletin_builder.py`.
2. Write the feature doc `src/app/storage/bulletin_store.md` (sections Behavior with a small Mermaid
   flow, Decisions, Invariants, Code map, Tests; header
   `<!-- code-doc` / `module: src/app/storage/bulletin_store.py` / `covers:` /
   `  - src/app/storage/bulletin_store.py` / `  - src/app/storage/migrations/versions/*bulletins*.py` / `-->`).
   Each Behavior rule names its tests (names below). Lines at most 100 characters. Register the doc
   in `docs/README.md`, `README.md` and `src/app/README.md` like the other code docs. In
   `builder.md` Code map, add one row for `bulletin build` storing (point to the new doc); do not
   repeat the rules there.
3. Failing tests (new file `tests/unit/test_bulletin_store.py`), run them and see them fail:
   - `test_save_and_get_ready_day` (round trip of payload, numbers, versions, status)
   - `test_save_replaces_the_day` (second save of the same day replaces, one row)
   - `test_posted_day_is_never_replaced` (row with telegram_message_id: save refused, row unchanged)
   - `test_skipped_day_is_stored_with_reason`
   - `test_latest_ready_skips_skipped_days`
   - `test_cli_build_stores_the_day` (`bulletin build --date D` without `--dry-run`, no `--write`:
     one ready row; follow how existing CLI tests in `tests/unit/test_bulletin_builder.py` set up a
     day and a session)
   - `test_cli_build_stores_a_skipped_day`
   - `test_cli_dry_run_stores_nothing`
   - `test_api_bulletin_by_date`, `test_api_bulletin_latest_ready`, `test_api_bulletin_404_and_400`,
     `test_api_bulletin_is_public` (no auth needed)
   - `test_bulletins_migration_round_trip` (upgrade creates, downgrade drops; same pattern as the
     world_change migration test)
   Command: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" tests/unit/test_bulletin_store.py | tail -5`
4. Code, smallest change in the current style:
   - `src/app/storage/models_sql.py`: model `BulletinRow` (table `bulletins`).
   - Alembic migration `..._add_bulletins.py` (create only when missing; downgrade drops), next in
     the revision chain (find the current head with the existing files; do not run alembic against
     any real database).
   - `src/app/storage/bulletin_store.py`: `BULLETIN_STORE_VERSION`, `BulletinRepo` with
     `save(...) -> bool` (False when refused), `get(day)`, `latest_ready()`.
   - `src/app/cli/main.py`: `bulletin build` without `--dry-run` stores (ready or skipped) after the
     same build (and the writer when `--write`); `--dry-run` keeps today's behavior and stores
     nothing. Print the same text/JSON as today. Log `bulletin_stored` (date, status, replaced or
     refused).
   - API route `GET /api/news/bulletin` in a new `src/app/web/routes/bulletin.py` (register it like
     the other routers) and add the path to the public set in `app.py`.
   - Keep functions small (CRAP under 10: complexity under 10 with tests).
5. Run, from the worktree, and fix anything that fails:
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" tests/unit/test_bulletin_store.py tests/unit/test_bulletin_builder.py tests/unit/test_bulletin_writer.py | tail -1`
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" -n auto | tail -1`
   - `PYTHONPATH=src make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python 2>&1 | tail -5`
   - `~/tools/unclebob/crapper/crapper --no-coverage src/app/storage/bulletin_store.py src/app/web/routes/bulletin.py`
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python scripts/check_code_docs.py --diff origin/master --strict; echo exit=$?`
     (alone and last; if it names a doc for a changed covered file, update that doc, rerun).

## Report (your final message)

Files changed, one line each; the failing-test output of step 3; outputs of step 5 (last lines,
exit codes); the migration revision id and its down_revision; anything you decided yourself or
could not do, one line each.
