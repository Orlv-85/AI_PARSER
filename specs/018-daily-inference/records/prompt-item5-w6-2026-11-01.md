# Prompt: spec 018 item 5, world stream step W6 text download (2026-11-01)

You implement step **W6** of the world stream as one PR. Repo: `ai-news-collector`
(`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`). Report in English. Do not merge, tag or deploy; no
ssh; **no paid calls** (Jev only through fakes).

## Rules

- Your own isolated worktree, branch `feat/018-world-w6-text` from `origin/master` (`git fetch
  origin` first). Never edit, commit, check out or pull in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`
  itself; you may read files there. Scratch worktrees named with `w6`; never remove one you did not
  create.
- Run Python as `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python`.
  pytest prints no summary by default: use `-o addopts="" ... | tail -1`.
- Read `AGENTS.md` first and follow it, and the ub-mode skill (`~/.claude/skills/ub-mode`; its
  "Repository rules come first" section applies). Doc first, then a failing test you saw fail for
  the expected reason, then the smallest code. Small patches in the surrounding style.
- Network: unit tests use fakes only. One manual smoke run may download at most 5 real pages (real
  publisher sites, through the archive downloader with its robots and bot agent rules).

## Read

1. `src/app/core/world/world.md` (states, `TextSource` seam, step B, Decisions), `src/app/core/world_screen.py`,
   `src/app/storage/world.py`, `src/app/core/world_collect.py`.
2. The archive downloader and capture: find `SourcePageDownloader`, `archive_articles`, the
   `archive import-db` path, `capture.md` (ER-9: archive texts are read, never published; the
   no-web-import invariant), `inspect_page` in `src/app/storage/article_evidence_cache.py`, and the
   daily archive job.
3. Plan `specs/018-daily-inference/records/plan-item5-world-sources-2026-10-31.md` section 5 (Text
   for retelling), 6.1 and 6.2 step 6; gate report `records/report-item5-w5-gate-2026-11-01.md`.

## What to build

- Doc first: extend `world.md` (Behavior with the flow `screened_in` -> download -> `text_ready` /
  `no_text`, Decisions, Invariants, Code map), each rule naming its tests.
- For the top `WORLD_TOP_N` ranked clusters still `screened_in` (only the cluster representative;
  never more than N pages a run, plus robots.txt), download the page through the existing archive
  downloader with a transient `Article` and store the text as an archive document version (origin
  `source_page`) as the plan says. Do not write a second crawler. Do not create `articles` rows.
- Outcomes: text extracted -> `text_ready`; robots denied, paywall, no extractable text, HTTP
  error -> `no_text` with the reason in `last_error` (prefix of your choice, distinct from
  `screen:` / `assess:`, and say how W5 requeue treats it); transport outage follows the archive's
  outage rule (no mass `no_text` on an outage).
- Fill the W5 `TextSource` seam so step B reads the stored archive text (cut to the Jev content
  limit). Keep step B behind the same world journal and caps; no change to the money rules.
- Command: either a new `ai-news world texts --date D [--dry-run]` or a step inside `world screen`
  (decide; say why). Not wired into the 04:00 job and no timer in this PR (W7 wires it).
- Tests from plan 6.2 step 6: `test_world_text_goes_through_archive_robots_and_bot_agent`,
  `test_world_text_blocked_by_robots_is_no_text`, `test_world_never_downloads_more_than_n`; plus
  outage, paywall/no text, seam feeds step B, and that retention prune of candidates keeps archive
  documents.
- Smoke: on a temp SQLite file, a handful of fixture candidates set to `screened_in` with real
  URLs, download at most 5 pages; counts by outcome in the PR body; delete the temp data.

## Checks

ruff on `src tests`; scoped tests; `make lint PYTHON=...`; full pytest `-o addopts="" | tail -1`;
`scripts/check_code_docs.py --diff origin/master --strict` and report its exit code (run it alone,
not through a pipe, after your last commit). mypy: fix `no-any-return` with `cast` or a typed
local, never `# type: ignore`. Advisory: `~/tools/unclebob/dryer/dryer` and
`~/tools/unclebob/crapper/crapper --no-coverage` on changed source files (report duplicates >= 0.8,
complexity >= 10; delete `.metrics/`).

## PR

Copy this prompt into `specs/018-daily-inference/records/` of your branch. Commit messages end with a
`Co-Authored-By:` line naming the model that wrote them. `gh pr create --base master`, title
`feat(018): world stream W6 text download through the archive`; body lists changes and checks with
counts, smoke numbers, and ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final message)

PR link, branch, worktree path; files; checks with counts and the doc-check exit code; smoke
numbers; how the archive storage is used (tables, origin, ER-9); anything decided by you (one line
each); questions for the owner only if about money or what readers see.
