# Prompt: 007 plan revision 2 (coordinator review of cad6368, 2026-10-19)

You are the **planner** for `007-daily-signals-brief`, continuing in your worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-007-plan` (branch `plan/007-daily-signals-brief`).
The coordinator reviewed commit `cad6368` (research, plan, tasks, dry-run). Planning only: no
changes under `src/`, `tests/`, `scripts/`. Never touch production.

## Accepted as is

D3 option (one list, "N outlets" / muted "via <publisher>"), P2 (`daily_signal_briefs` table), P3
(one-liner rule), P4 (quiet-day template line), P5 (folding, diffuse spikes dropped), P6 with
per-model ledger prices, validation rules 1-8, job integration, tests plan.

## Fix before implementation

### R1 (must) Brief picks reviews and SEO pages over news

On 10-16 the pro brief spends 2 of 5 sentences on hardware reviews (Surface Laptop Ultra, RTX
Spark) and skips the New releases (Glimpse, MAI-Base-2, d1-ultra); on 10-15 sentence 4 comes from
the emergent.sh "Gemini 4 Argon vs ..." comparison page. The prompt's order "more outlets first"
causes this, and event types cannot filter it (the reviews are `product_launch`, the SEO page is
`model_release` in the snapshot).

Change the prompt ordering to what happened, not outlet count alone: releases, launches, funding,
deals, incidents, policy first (multi-outlet before single-source within them); reviews,
comparisons, benchmarks roundups, guides and opinion only when nothing else is left. Keep every
other prompt rule. Bump `BRIEF_VERSION` to `daily-signals-brief-2` in the plan.

Re-measure with `deepseek-v4-pro` only on 10-13, 10-15, 10-16 (hard cap $0.05 at ledger prices)
and add a short section to `dry-run.md`: the 3 briefs verbatim, the same grounding check, and the
diff against revision 1 (which sentences changed and why). If a normal day loses a strong
multi-outlet release, say so.

### R2 (must) `--max-usd` must stay the total for the run

The plan gives the brief its own cap `min(0.05 * days, X)` next to the extraction cap X, so one
`--max-usd 0.45` run could spend up to $0.90. Make `--max-usd` the total: the brief cap is
`min(0.05 * days, X - extraction spend of this run)`; when that is <= 0 the briefs are skipped with
reason `brief_budget_exhausted`. X is always set (CLI flag or `settings.daily_signals_max_usd`,
default `0.50`), so the nightly run follows the same rule and its maximum stays X. Update plan (Job
integration, Cost) and the T3.1 tests list.

### R3 (should) Put the spec deltas into `spec.md`

`spec.md` is the contract the implementer reads first. Edit it on your branch to match the plan:
FR-004 (P3 rule, quote-sourced lines in quotes), US3 (spike reason = largest D story; diffuse company
spikes dropped), FR-006 (template opening line), FR-002/SC-005 already say $0.05. Mark the
"Spec deltas" section in `plan.md` as applied.

## Then

Commit, push, stop, and report: the new briefs for the 3 days in one line each (what changed),
spend, and any change to cost or risks. Files ASCII; keep documents short.
