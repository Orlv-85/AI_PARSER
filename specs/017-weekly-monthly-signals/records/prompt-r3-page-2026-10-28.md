# Prompt: 017 release R3, the /weekly page (T020) (2026-10-28)

You are the **implementer** (background agent, Sonnet) for the 017 coordinator. You did not write the
plan; follow it. One PR, do not merge, do not tag. Production is read-only for you.

State: R2 is live as v0.1.134 (PRs #132, #133). On prod the flag is on and two weeks are stored:
2026-10-12 (`building_history`) and 2026-10-19 (`ready`: 387 items, 7/7 days, 76 publishers,
`trend_source` `sunday_snapshot`). The API `GET /api/news/period-signals` and `/index` return them.
Readers see nothing yet. This PR adds the page readers see.

## Read first

`AGENTS.md`; `specs/017-weekly-monthly-signals/plan.md` ("Web", "Rollout" step 3, "Decided", owner
answers); `tasks.md` Phase 3 (T020); `src/app/core/periodic/signals_period.md`;
`src/app/web/pages.md` (the page doc: how `/` and its signals block render, static files, auth
public list, escaping); the daily signals rendering of `/` (`git grep -n "signals" src/app/web/*.py
src/app/web/templates src/app/web/static | head -50` and follow it); `src/app/web/routes/period.py`,
`src/app/web/models.py` (period response models); `src/app/storage/period_signals.py`;
the route table, auth and packaging tests (`git grep -ln "route_table\|package_data\|static" tests/unit`).

## Scope: T020 exactly

- `src/app/web/period_view.py`: server HTML for one stored week from the same stored row the API
  reads (no provider, no compute on request). Sections in this order: coverage line (with "quiet
  week" line when `quiet`), top stories, top entities by group, New this week, Rising and Cooling,
  event-type mix with delta. A section whose state is not `ready` shows one short plain reason line
  (e.g. comparison hidden for `low_publisher_coverage`, or "first week, no comparison" for
  `building_history`), never an empty chart. Items link to their articles (http(s) only, escaped
  text) and days link to `/?date=YYYY-MM-DD`.
- `GET /weekly` (latest week the API would pick by default) and `GET /weekly?week=YYYY-MM-DD`
  (a Monday; any other date redirects to its Monday or shows unavailable - your call, record it);
  public like `/`; no row or corrupt payload: 200 with an "unavailable" page, never 500.
  A simple week picker as plain links from the index (previous / next / list), no client re-render.
- Template `period.html` (or the template layout the web package uses), `static/js/period.js` only
  if needed, `static/css/period.css`; reuse classes of the daily signals block where it fits; no
  inline CSS/JS (pages.md rule).
- Header nav link "Weekly" only when at least one stored week exists; on `/` one line under the
  daily signals block: "Week of Oct 19-25: weekly signals" linking to `/weekly` (latest week). The
  legacy "Weekly AI Analytics" preview on `/` and the `/weekly-ai-analytics*` pages stay unchanged
  (they go in R5).
- Docs: `web/pages.md` first (Behavior rules with tests, Code map); `signals_period.md` (Behavior of
  the page states, extend `covers:` with `src/app/web/period_view.py`); `docs/period-signals.md`:
  fix the backfill line - it computes completed weeks only, so on 2026-10-28 `--backfill 3` stored
  10-12 and 10-19 (10-05 skipped as history); 10-26 is computed by the nightly step from Monday
  2026-11-02.
- Tests: page ready, `building_history`, partial, unavailable (no rows), corrupt row (200), escaped
  text and only http(s) links, `?week=` handling, nav link hidden without rows and shown with rows,
  the line on `/`, route table, packaging data (new static/template files ship in the wheel), auth
  public list.

## Rules

- Do not touch storage, compute, CLI, scripts, workflows, compose, settings.
- What readers see is a product matter: keep to the plan; wording of labels is yours (short, plain
  English like the daily block). Anything beyond the plan that readers would notice: stop and report
  as a yes/no with a recommendation.
- Unclear vs. code: decide, write "decided 2026-10-28 (agent): <reason>" in the doc, list it.
- Keep code ASCII; match the style of the daily block code.

## Checks (from the worktree)

```
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b feat/017-r3-weekly-page ../AI_PARSER-wt-017r3 origin/master
cd ../AI_PARSER-wt-017r3
PYTHONPATH=src make lint PYTHON=../AI_PARSER/venv1/bin/python
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider -o addopts="" | tail -1
../AI_PARSER/venv1/bin/python scripts/check_code_docs.py --diff origin/master --strict
```

Use `PYTHONPATH=src` (without it the venv imports the main folder's code). Render the page locally
once on SQLite with a stored week (the R2 test helpers seed one) and save the HTML to the PR as a
short excerpt or describe what you saw; no screenshot tooling needed. No git writes in the main folder.

## Commit and PR

Commit `feat(017): R3, /weekly page and nav link` ending with
`Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; add this prompt file at its path under
`specs/017-weekly-monthly-signals/records/`; push; `gh pr create --base master` with: what readers
see (states, nav, the line on `/`), decided items, checks. Body ends with
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Wait for CI
(`gh pr checks <N> --watch --interval 30`); fix real failures; do not call a CI failure "local only"
without proof.

## Report (final answer)

PR URL and SHA; CI result; files with line counts; what readers see in each state; decided items;
full gate last line; anything for the owner (yes/no with recommendation) or unclear.
