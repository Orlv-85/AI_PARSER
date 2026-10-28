# Prompt: 017 release R2, PR 1 of 2: code doc, model, trend_delta, pure compute (T010-T012) (2026-10-28)

You are the **implementer** (background agent, Sonnet) for the 017 coordinator. You did not write the
plan; follow it. One PR, do not merge, do not tag. Production is read-only for you (you need no prod
access in this PR).

Release R2 is two PRs: this one (T010-T012: pure code, no storage, no CLI, no web) and a second one
(T013-T015: storage, CLI, nightly step, API). Decided 2026-10-28 (coordinator): split at the storage
boundary so the pure rules are reviewed before anything writes to the DB. Nothing in this PR is
reachable from the app at runtime yet.

## Read first

`AGENTS.md` ("Feature Docs Next To Code" in full); `specs/017-weekly-monthly-signals/spec.md`;
`plan.md` ("Design of the new feature" to the end, "Decided", "Owner answers"); `tasks.md` Phase 2;
`src/app/core/daily/signals.md` (current 006/007 behavior: Rising/Cooling, New, top stories, events,
coverage, `COMPARABLE_FROM`); `src/app/core/daily/signals_compute.py`, `signals_model.py`,
`signals_stories.py`; `tests/fixtures/daily_signals/README.md`; the daily signals tests
(`git grep -l signals_compute tests/`); `scripts/check_code_docs.py`; `docs/troubleshooting.md`.

## Scope: T010, T011, T012 exactly

**T010.** Code doc first: `src/app/core/periodic/signals_period.md` with the `<!-- code-doc` header
(`module: src/app/core/periodic/signals_period.py`; `covers:` only globs whose files this PR ships,
i.e. `src/app/core/periodic/*.py`). Sections per AGENTS.md: Behavior (week/month definitions,
completed periods only, status precedence `unavailable` / `partial` / `building_history` / `ready`,
coverage rules with the `PeriodThresholds` constant names, each section's rule; Mermaid flow; each
rule names its tests), Decisions (from `plan.md` "Decided" plus the owner answers, one or two lines
each, no history), Invariants (pure, $0, no provider import, no DB), Code map, Tests. Only names that
exist in this PR (the checker fails on others): describe storage/CLI/web as "next PR" in plain words
without backticked names that do not exist yet. Register the doc in `docs/README.md` (Code docs
table), `README.md` (Documentation) and `src/app/README.md`. Create the package
`src/app/core/periodic/` with `__init__.py`, `signals_period.py` (main module: docstring names the
doc; thin public entry for this PR, e.g. the compute function re-exported - keep it minimal),
`period_model.py` (`PeriodThresholds` with week and month values from the plan table, `PeriodInput`,
week/month bounds, status function). Tests: bounds (Monday start, Sunday end, year change, month
lengths 28/29/30/31), status precedence, missing day is not zero.

**T011.** Extract the Rising/Cooling computation (`trend_delta` in the plan) from
`core/daily/signals_compute.py` into a shared function with **no behavior change**: no
`METHODOLOGY_VERSION` bump, all daily tests unchanged and passing, payload hashes of the 006 fixtures
unchanged. Prove it: before your edit compute `payload_hash(compute_snapshot(...))` for every fixture
day the daily tests build, save the list, and compare after the edit (put the before/after table in
the PR body). Put the helper where 006 code can import it without importing `core/periodic`
(recommended: stays in `core/daily/`, e.g. `signals_compute.py` or a new `signals_trend.py`; your call,
record it as "decided 2026-10-28 (agent)"). Update `signals.md` Code map for the move. Verify in the
code whether the daily Rising window ending on D includes D, and write the answer with the line
reference into `signals_period.md` (Decisions) - this decides whether the weekly risers can reuse the
Sunday snapshot (plan: "Open for the implementer to verify").

**T012.** `src/app/core/periodic/period_compute.py`, pure functions over `PeriodInput`: coverage
line, top stories merged across days (event type + entity key; ranked by distinct publishers, then
days; caps), top entities by group with minimums, New union (confirmed first, first-seen day), weekly
risers/coolers (from the Sunday snapshot if its methodology is current, else the T011 helper with the
week bounds), event-type mix with delta, publisher-breadth suppression (`low_publisher_coverage`),
`payload_hash` (reuse the daily one), `PERIOD_METHODOLOGY_VERSION`. Month risers and month-only
rules are R6, not now (bounds and thresholds for months exist from T010). Fixture weeks built from
`tests/fixtures/daily_signals/` (do not copy fixture data; build inputs from them in a helper under
`tests/`; if you need new fixture files put them in `tests/fixtures/period_signals/`). One test per
rule named in the doc; also hash stability (same input, same hash; reordering days does not change
it) and "rising equals the Sunday snapshot" on the fixture week.

## Rules

- Do not touch storage, migrations, CLI, web, scripts, workflows, settings. No new setting yet.
- If the plan is unclear or wrong against the code, decide, write "decided 2026-10-28 (agent):
  <reason>" in `signals_period.md`, and list it in the report. Product or money questions: stop and
  report them as yes/no with a recommendation.
- Keep code ASCII; match the style of `core/daily/`.

## Checks (from the worktree)

```
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b feat/017-r2a-period-compute ../AI_PARSER-wt-017r2a origin/master
cd ../AI_PARSER-wt-017r2a
make lint PYTHON=../AI_PARSER/venv1/bin/python
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider -o addopts="" | tail -1
../AI_PARSER/venv1/bin/python scripts/check_code_docs.py
```

`pytest -q` prints no summary line here; use the command above. No git writes in the main folder.

## Commit and PR

Commit `feat(017): R2a, period model, trend_delta helper and pure period compute` ending with
`Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; push; `gh pr create --base master` with:
what each task added; the T011 hash table (before/after, all equal); the D-included answer with line
reference; the list of "decided (agent)" items; checks. Body ends with
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Wait for CI
(`gh pr checks <N> --watch --interval 30`); fix real failures (`gh run view <id> --log-failed`); do
not call a CI failure "local only" without proof (known before: mypy no-any-return across modules,
check_code_docs strict diff).

## Report (final answer)

PR URL and SHA; CI result; new files and line counts (src / tests); T011 hash proof summary; the
D-included answer; "decided (agent)" items; full gate last line; anything left for R2b or unclear.
