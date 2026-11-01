# Prompt: spec 018 item 2, bulletin builder with phrase library, dry run (2026-11-01)

You implement item **2** of spec 018 as one PR, branch `feat/018-bulletin-builder`. Repo:
`ai-news-collector` (`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`). Report in English. Do not
merge, tag or deploy.

## Rules

- Your own isolated worktree, branch from `origin/master` (`git fetch origin` first). Never edit,
  commit, check out or pull in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself; you may read
  files there. Scratch worktrees named with your step; never remove one you did not create.
- Run Python as `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python`.
  pytest prints no summary by default: use `-o addopts="" ... | tail -1`.
- Read `AGENTS.md` first and follow it, and the ub-mode skill (`~/.claude/skills/ub-mode`; its
  "Repository rules come first" section applies). Doc first, then a failing test you saw fail for
  the expected reason, then the smallest code. Small patches in the surrounding style.
- **No paid calls**, no ssh, no network in tests (fakes and fixtures only).
- Another agent works in parallel on a different step of spec 018; if `src/app/cli/main.py`
  conflicts at PR time, rebase on `origin/master` and resolve.

## Checks

ruff on `src tests`; scoped tests; `make lint PYTHON=...`; full pytest `-o addopts="" | tail -1`;
`scripts/check_code_docs.py --diff origin/master --strict` run alone after your last commit, report
its exit code. mypy: fix `no-any-return` with `cast` or a typed local, never `# type: ignore`;
`bash -n` on changed scripts. Advisory: `~/tools/unclebob/dryer/dryer` and
`~/tools/unclebob/crapper/crapper --no-coverage` on changed source files (report duplicates >= 0.8,
complexity >= 10; delete `.metrics/`).

## Read

1. `specs/018-daily-inference/spec.md` (editorial rules ER-1..ER-12, User Story 1, FR-001..FR-006,
   FR-016, FR-019, implementation order) and `specs/018-daily-inference/voice.md` (structure,
   areas, fixed phrases, never-list, samples).
2. Item 1: `src/app/core/bulletin/world_change.md` and `.py`, `src/app/storage/world_change.py`,
   report `specs/018-daily-inference/records/report-item1-2026-10-31.md` (thresholds: proposed
   `world_change` 0.7, harm 0.7).
3. Daily signals: `src/app/core/daily/signals.md` (day type: quiet, partial, unavailable, busy
   median; counts `model_release`, `product_launch`, items) and the published digest of a day.
4. World stream: `src/app/core/world/world.md` (assessed world candidates, keyed by hash).

## What to build

- New feature doc next to the main module (for example `src/app/core/bulletin/builder.md`), with
  Behavior (Mermaid flow), Decisions, Invariants, Code map, Tests; registered in `docs/README.md`,
  `README.md`, `src/app/README.md`.
- **Phrase library as JSON** (`voice.md` says item 2 moves it): a data file with openings by day
  type, numbers line, positive rubrics, reactions by kind and area, closings, cut-headline marker.
  Then edit `voice.md` so it keeps rules and samples and points to the JSON for the phrases (one
  source per fact). Loader validates the JSON (test). A "never" word check runs on every phrase
  (ER-4 list in `voice.md`; test).
- **Builder** (pure core, storage at the edge): input = the day's digest articles with their
  `world_change_assessments` answers, plus assessed world candidates **only when** the new setting
  `WORLD_STREAM_IN_BULLETIN` is on (default off; FR-016/FR-018: the world stream enters after the
  first days check). Output = a bulletin object: day number (FR-006: days since 2022-11-30), masthead,
  headline of the day, opening by day type, numbers line, sections per FR-003 with caps (Key results
  max 4 with model launches max 2, one positive rubric, Cooperation max 2, Isolated incidents count
  with an optional plain line about an incident caused by people), reactions per `voice.md` limits
  (at most one per story, three per issue), closing, full-report link with the item count.
  Thresholds as named constants (start with item 1's 0.7 / 0.7). One story per event (dedup), rank
  by confidence then outlet count. Harm stories (ER-11) are only counted: never headline, never
  rubric, never reaction (test). Phrase variants chosen by date so neighbouring days differ (test).
- **Title-only stories**: the story text in item 2 is the article title with outlet and link (the
  model writer is item 3). Headline of the day: from the chosen story's title, at most 8 words in
  capitals; a longer one is cut at a clause boundary with the ER-8 marker and footnote (test).
- **Day status**: `partial` or `unavailable` signals -> no bulletin, reason logged (User Story 1
  scenario 3); quiet day -> quiet opening, empty sections left out (scenario 2).
- **CLI**: `ai-news bulletin build --date D --dry-run` prints the bulletin as plain text (Telegram
  style of `voice.md`) and, with `--json`, the object. Item 2 has only the dry run: no storage, no
  job, no page (item 4). No model calls.
- Tests on fixtures that cover each acceptance scenario of User Story 1 that applies without the
  writer (1, 2, 3, 5), the caps, dedup, the switch, the day number (Day 1429 = 2026-10-29).
- Smoke: run the dry run on the owner's local data **read-only** if a day with a digest and
  `world_change_assessments` exists (find out how settings choose the database; do not write to it;
  if no assessed day exists locally, say so and skip). Put the printed bulletin in the PR body.

## PR

Copy this prompt into `specs/018-daily-inference/records/` of your branch. Commit messages end with
a `Co-Authored-By:` line naming the model that wrote them. `gh pr create --base master`, title
`feat(018): bulletin builder with phrase library (item 2)`; body lists changes, checks with counts,
the smoke bulletin, and ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final message)

PR link, branch, worktree path; files; checks with counts and the doc-check exit code; the smoke
bulletin; anything decided by you (one line each); questions for the owner only if about money or
what readers see (for example a phrase or a section rule `voice.md` does not settle), each as yes/no
with a recommendation.
