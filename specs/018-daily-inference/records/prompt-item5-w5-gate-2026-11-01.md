# Prompt: spec 018 item 5, W5 gate run on one real GDELT day (2026-11-01)

You measure step A of the world stream (title screen, merged in PR #188) on one real day. Repo:
`ai-news-collector` (`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`). Report in English. Do not
merge, tag or deploy; no ssh; no commits or PRs (the coordinator saves your report).

## Money and network (approved)

- Paid: Jev step A only, through `ai-news world screen`, inside the world journal's $0.10 per UTC
  day cap (approved by the owner). Expected about $0.03-0.05. Run it **once** without
  `--dry-run`; if it stops on the journal (5xx), do not rerun with a new budget: report it.
- Network: GDELT raw files for one UTC day (about 192 files, about 820 MB, streamed, nothing raw
  kept), via `ai-news world collect`.

## Rules

- Your own worktree from `origin/master` (`git fetch origin` first), named with `w5-gate`. Never
  edit, commit, check out or pull in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`; you may read
  files there. Never remove a worktree you did not create; remove yours at the end.
- Run Python as `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python -m app.cli.main ...`
  (or the module path the `ai-news` entry point uses; find it in `pyproject.toml`).
- Database: a temporary SQLite file in your scratchpad, never the owner's local PostgreSQL or the
  main folder's `data/`. Find how settings choose the database and the `data/` root (`world.md`,
  settings module) and point both at your scratchpad.
- Key: export only `JEV_API_KEY` from `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.env`
  (for example `grep '^JEV_API_KEY=' ... | cut -d= -f2-`); never print it, never load the whole
  `.env` (it points at other databases).

## Steps

1. Read `src/app/core/world/world.md` (Behavior, Cost cap, wedged journal) and the plan
   `specs/018-daily-inference/records/plan-item5-world-sources-2026-10-31.md` sections 2-4.
2. Migrate the temp database; `world collect --date 2026-10-31`; record the summary line
   (files, rows, matched, kept, new, missing, partial) and wall time.
3. `world screen --date 2026-10-31 --dry-run`, then once without `--dry-run`; keep both JSON
   summaries and the `world_screen_usage` line.
4. Measure: requests; input tokens per request (mean, p50, p95) against the plan's 300; output
   tokens; `cost_usd` and `total_committed_usd` against $0.03-0.04; `in / screened`; clusters vs
   candidates; how many late outlets followed; Jev rejected or failed requests (title-only state
   accepted or not).
5. **Precision, blind.** Before looking at Jev results, export a random sample of 120 screened
   candidates (seed fixed, stated) as title + domain + language only, shuffled, and label each
   `in` / `out` by the spec 018 scope (AI in human life: what AI changed for people; read
   `specs/018-daily-inference/spec.md` scope and FR-001, and the label definitions in
   `records/prompt-item1-labels-2026-10-31.md`). Write labels to a file first, then join with Jev's
   `screen_confidence`. Report precision and recall of step A at the current
   `SCREEN_THRESHOLD`, and at 0.3, 0.4, 0.6, 0.7; how many of your `in` labels would be lost.
   Give 10 examples of disagreement (title, your label, confidence).
6. Top N: how many clusters are `screened_in` and how many would reach step B (`WORLD_TOP_N`);
   list the top 20 titles with confidence and outlet count.

## Report (final message, as Markdown the coordinator can save as
`specs/018-daily-inference/records/report-item5-w5-gate-2026-11-01.md`)

Commands run (without the key); collect summary and time; screen summaries; token and cost
numbers vs the plan; precision table by threshold; disagreements; top 20; recommendation for
`SCREEN_THRESHOLD` (keep or change, with the numbers); anything surprising. Delete the temp
database, journal and downloaded data at the end and say so.
