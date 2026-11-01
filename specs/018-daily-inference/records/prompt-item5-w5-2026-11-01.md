# Prompt: spec 018 item 5, world stream step W5 Jev steps A and B (2026-11-01)

You implement step **W5** of the world stream as one PR. Repo: `ai-news-collector`
(`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`). Report in English. Do not merge, tag or deploy; no
ssh; **no paid calls** (Jev runs only through fakes in this PR; the real measurement is a separate
gate step after review).

## Rules

- Work only in your own isolated worktree (`git fetch origin` first, branch
  `feat/018-world-w5-jev` from `origin/master`). Never edit, commit, check out or pull in
  `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself; you may read files there. If you make a
  scratch worktree, name it with `w5` and never remove one you did not create.
- Run Python as `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python`.
  pytest prints no summary by default: use `-o addopts="" ... | tail -1`.
- Read `AGENTS.md` first and follow it, and follow the ub-mode skill
  (`~/.claude/skills/ub-mode`; its "Repository rules come first" section applies). Test first: the
  doc states the rule, then a failing test (run it, see it fail for the expected reason), then the
  smallest code. Small patches in the surrounding style.
- Network: none needed. Unit tests use fixtures and fake transports only.

## Read

1. `src/app/core/world/world.md`, `src/app/core/world/filter.py`, `src/app/core/world/gdelt.py`,
   `src/app/core/world_collect.py`, `src/app/storage/world.py` and their tests (W1-W4).
2. `src/app/core/bulletin/world_change.md` and `world_change.py`, `src/app/storage/world_change.py`
   (item 1: the four FR-001 questions, keyed by `url_canonical_hash`, `PilotJournal` caps).
3. `src/app/core/jev.py`, `src/app/core/provider_costs.py` and how the provider journal enforces
   a daily cap (find the digest's Jev cap and how `world_change` opens its journal).
4. Plan `specs/018-daily-inference/records/plan-item5-world-sources-2026-10-31.md`: section 4
   (cost, assumptions), 6.1 (Jev, Cost cap, Failure handling, ranking) and 6.2 step 5.
5. Spec `specs/018-daily-inference/spec.md` FR-001, FR-003, FR-012, FR-016.

## What to build

Doc first: extend `world.md` (Behavior with the flow from `new` to `screened_out` /
`screened_in` / `assessed` / `failed`, Decisions, Invariants, Code map), each rule naming its tests.

- **Step A, title screen**: one Jev question `ai_relevant` (probability that the story is about
  AI in human life, the scope of spec 018) on title + source domain + language only, for every
  candidate in state `new`. One representative per `cluster_key` is screened; the others of the
  cluster follow its result (decide and document how). Threshold as a named constant; state
  `screened_in` / `screened_out`, `screen_confidence` stored. Separate question version constant;
  `RUBRIC_VERSION` and `WORLD_CHANGE_VERSION` untouched. Find out from `jev.py` whether a request
  without content is accepted; if not, say how you handled it.
- **Ranking and step B**: rank `screened_in` by confidence x outlet count (cluster size), then
  human-life themes if stored (if W2-W4 do not keep themes, say so and rank without them; do not
  add a migration only for this unless needed). Top N (`WORLD_TOP_N = 100`) get the four FR-001
  questions of item 1, reusing `world_change` (state, request, validation, storage by hash) rather
  than copying it. Step B needs text: W6 brings the text download, so in W5 step B runs only for
  candidates that already have text (`text_ready`); with none, it does nothing and says so in the
  summary. Make the text source a small seam W6 can fill.
- **Cost cap**: world Jev budget `$0.10/day` (approved by the owner) as its own line in the provider
  journal, separate from the digest's Jev cap and from `bulletin assess`; at the cap the run stops
  and logs `world_cost_cap`; unprocessed candidates stay pending for the next run (up to 2 days, as
  the plan says).
- **Failures**: Jev failure leaves candidates pending (`attempts`, `last_error`), no retry loop;
  journal stop ends the run like `world_change` does.
- **Command**: `ai-news world screen --date D [--max-usd X] [--dry-run]` (or a subcommand name that
  fits the existing `world` group better; say which), one JSON summary (screened, in, out, assessed,
  skipped_no_text, failed, not_attempted, cost_usd, tokens per step if the journal records them).
  Real run needs `JEV_API_KEY` (exit 2 without). `--dry-run` sends nothing and writes nothing.
  Not wired into the 04:00 job and no new timer in this PR (the job stays collect-only; wiring
  comes with W6/W7). State this in the doc.
- Tests from plan 6.2 step 5: `test_screen_sends_title_and_domain_only`,
  `test_stage_b_only_for_top_n_with_text`, `test_world_cap_stops_requests`,
  `test_world_jev_failure_leaves_candidates_pending`; plus cluster follow, ranking order, dry run,
  missing key, separate journal line from the digest cap.

## Checks

ruff on `src tests`; scoped tests; `make lint PYTHON=...`; full pytest `-o addopts="" | tail -1`;
`scripts/check_code_docs.py --diff origin/master --strict` (look at the exit code, not through a
pipe). mypy: names from `app.*` are `Any`; fix `no-any-return` with `cast` or a typed local, never
`# type: ignore` (see `docs/troubleshooting.md`). Advisory: `~/tools/unclebob/dryer/dryer` and
`~/tools/unclebob/crapper/crapper --no-coverage` on changed source files (report duplicates >= 0.8
and complexity >= 10; delete `.metrics/` afterwards).

## PR

Copy this prompt into `specs/018-daily-inference/records/` of your branch. Commit messages end with a
`Co-Authored-By:` line naming the model that wrote them. `gh pr create --base master`, title
`feat(018): world stream W5 Jev title screen and FR-001 for top N`; body lists changes and checks
with counts, and ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final message)

PR link, branch, worktree path; files; checks with counts; the Jev no-content finding; how the
cap line is separated from the digest's; what the gate run (real day, paid, after review) should
measure and the exact command for it; anything decided by you (one line each); questions for the
owner only if about money or what readers see.
