# Prompt: spec 018 item 5, world stream step W3 storage (2026-11-01)

You implement step **W3** of the world news plan as **one PR**. Repo: `ai-news-collector`
(`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`). Report in English. Do not merge, tag or deploy; no
ssh; no paid calls; no network beyond git/gh.

## Rules

- Work only in your own isolated worktree from `origin/master` (`git fetch origin` first). Never
  edit, commit or pull in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself; you may read files
  there (prompts, `venv1`). Run Python as `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python`
  (venv1 points at the main folder's src). pytest prints no summary by default: use
  `-o addopts="" ... | tail -1`.
- Read `AGENTS.md` first and follow it: the feature doc **before** code, small patches in the style
  of the surrounding code, ASCII code, every rule names its tests.

## Read

1. Plan on `origin/master`: `specs/018-daily-inference/records/plan-item5-world-sources-2026-10-31.md`,
   sections 6.1 (Storage, Retention, Failure handling) and 6.2 step 3.
2. `specs/018-daily-inference/spec.md` FR-014..FR-018 (FR-016: the world stream never enters
   `articles`, `/daily` and its sources stay untouched).
3. Current code: `src/app/core/world/world.md`, `filter.py`, `gdelt.py` (W1, W2 merged);
   `src/app/storage/world_change.py` and migration `b8e2d4f61a07_add_world_change_assessments.py`
   (latest head, item 1) and `src/app/storage/archive.py` + `e7b4c2a9d150_add_article_archive.py`
   with its round-trip test for patterns; `models_sql.py`; where `canonicalize` lives for `articles`.

## Scope (W3 only)

- Migration on top of head `b8e2d4f61a07`: tables `world_candidates` and `world_files` with the
  columns of plan 6.1 (`url_canonical_hash` unique, computed with the same canonicalize as
  `articles`; `state` values as listed there; `world_files` keyed by `(stamp, kind)`, plus a
  `missing` state for files per the failure rule). Works on SQLite and PostgreSQL.
- Storage module `src/app/storage/world.py` (or the name that fits the existing modules): upsert of
  candidates by hash (a repeat keeps `first_seen_at`, does not reset state), record and read file
  states (so W4 can skip processed stamps), state transitions with allowed-transition check, prune
  of candidates older than the retention constant (30 days; archive documents are not touched).
- Doc: extend `src/app/core/world/world.md` (Behavior rules with tests, Invariants, Code map with
  tables and migration). Keep FR-016 as an invariant with a test.
- Tests from plan 6.2 step 3: `test_world_candidate_dedup_by_canonical_hash`,
  `test_world_prune_keeps_archive`, a migration round trip like
  `test_article_archive_migration_round_trip`, `test_world_tables_not_read_by_digest` (no import of
  the world storage from web/digest code); plus transition and file-state tests.
- Not in scope: `ai-news world collect`, job script, timer (W4), any Jev call (W5), text download
  (W6). Do not change `world_change_assessments` keys now; note in the report what W5 will need.

## Checks

ruff on `src tests`; scoped tests; `make lint PYTHON=...`; full pytest with `-o addopts="" | tail -1`
for the pass count; `scripts/check_code_docs.py`; `alembic upgrade head` and `downgrade -1` on a
temp SQLite file.

## PR

Copy this prompt into `specs/018-daily-inference/records/` of your branch. Commit messages end with
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. `gh pr create --base master`, title
`feat(018): world stream W3 storage`; body lists changes, checks with counts, and ends with
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final message)

PR link and branch; worktree path; files; checks with counts; anything decided by you (one line
each); what W4 and W5 should know about the API; questions for the owner only if about money or
what readers see.
