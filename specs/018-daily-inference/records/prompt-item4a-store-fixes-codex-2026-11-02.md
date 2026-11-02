# Prompt (Codex fix, gpt-6.1-sol high, resumed session): item 4a review fixes (2026-11-02)

Same worktree and rules as before (`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4a-store`;
no commit, push, gh or network). The review (Astra) asked for changes. Doc first, then failing
tests (run them, see them fail), then the smallest code.

1. Article ids (P2, FR-007). Add `article_id: int | None = None` to `Candidate`
   (`src/app/core/bulletin/builder.py`), filled by `load_day_input` for digest articles
   (`src/app/storage/bulletin_input.py`); world candidates keep None. Add
   `article_ids: list[int] = field(default_factory=list)` to `Story`: the ids of all members of the
   event, in member order, Nones left out. Update `builder.md` (Stories rule + Code map) and
   `bulletin_store.md` (payload). Tests: `test_story_carries_article_ids` (builder, two members of
   one event), and assert explicit ids in `test_save_and_get_ready_day` and
   `test_api_bulletin_by_date`. Check the writer packet does not change (`test_bulletin_writer.py`
   must pass unchanged, except where it compares a full `as_dict`).
2. Stale session after a refused save (P2). On refusal, refresh the existing row in the session
   (e.g. `session.expire`/`refresh` of the identity, or `populate_existing` on a reselect) so a later
   `get()` in the same session shows the stored row. Test
   `test_refused_save_refreshes_the_session`: session A loads the day, session B sets
   `telegram_message_id = 42` and commits, A's save returns False, A's `get(day)` shows 42 and the
   old payload. (This also covers the surviving `populate_existing` mutant.)
3. `replaced` in the log (P3). Drop the `replaced` field (a pre-read cannot be exact under races);
   log `bulletin_stored` with `date`, `status`, `refused`. Doc decision, one line, "decided
   2026-11-02 (agent)".
4. Surviving mutant 503 -> 500: test `test_api_bulletin_storage_failure_is_503` (a SessionLocal
   that raises `SQLAlchemyError`).
5. PostgreSQL: add `tests/integration/test_bulletin_store_postgres.py` following
   `tests/integration/test_article_upsert_postgres.py` (skipped without `AINEWS_TEST_POSTGRES_URL`;
   CI sets it): migration upgrade creates the table; save, replace, posted row refused, refusal
   returns False. Name it in the doc.
6. Checks (report outputs, last lines and exit codes):
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" tests/unit/test_bulletin_store.py tests/unit/test_bulletin_builder.py tests/unit/test_bulletin_writer.py tests/unit/test_web_route_table.py | tail -1`
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" -n auto | tail -1`
   - `PYTHONPATH=src make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python 2>&1 | tail -5`
   - ub-mode tools (new rule from today), from the worktree root:
     - `~/tools/unclebob/crapper/crapper src/app/storage/bulletin_store.py src/app/web/routes/bulletin.py src/app/core/bulletin/builder.py src/app/storage/bulletin_input.py`
       (with coverage; report every function of these files with CRAP >= 10 and whether you changed it)
     - `~/tools/unclebob/dryer/dryer --threshold 0.8 src/app/storage/bulletin_store.py src/app/web/routes/bulletin.py`
     - `~/tools/unclebob/mutator/mutator --test-command "/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_bulletin_store.py" src/app/storage/bulletin_store.py`
       (if the command needs `PYTHONPATH=src`, export it before the run instead of putting it in the
       string). Kill every survivor with a test, or give a one-line reason it cannot be killed.
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python scripts/check_code_docs.py --diff origin/master --strict; echo exit=$?` (alone and last).

Report: files changed, one line each; failing-test output before the code; check outputs;
mutator: sites, killed, survived, uncovered, and what you did with each survivor.
