# Prompt: offline pilot 3, summary prompt that keeps every detail inside its quote (2026-10-23)

You work in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. Read `AGENTS.md` first. The owner writes
Russian and takes part minimally; report to the session that sent you this prompt.

## Why

Pilots 1 and 2 (`docs/report-jev-entailment-pilot-2026-10-23.md`,
`docs/report-jev-repair-pilot-2026-10-23.md`) found that about a third of published daily summaries
carry a detail that is not in their paired quote (a speaker or vendor, a product name, a number),
and that a stricter review gate would cost ~20% of the digest. Decision: keep the review as it is
and fix the cause in the summary prompt instead.

Likely cause: the attempt-0 text in `grounded_summary` (`src/app/core/daily/enrichment.py`, the
`if attempt == 0` block) and `SUMMARY_INSTRUCTIONS` (`src/app/core/daily/reenrich_pilot.py:91`) ask
the model to "attribute vendor claims", but nothing requires the attributed actor (or any other
name or number) to be inside the chosen quote.

This pilot measures prompt variants offline. It does not change `src/`; the code change is a later
phase with its own prompt, after review of this report.

Spend: hard cap $0.30 for all new calls (DeepSeek + Jev) in this pilot.

## Hard rules

- Prod (`ssh ai-news`) is read-only: `scp` from the server and `SELECT` only. No writes, no restarts.
- No changes under `src/` or `tests/`. Scripts and private data stay in `data/summary-grounding-pilot/`
  of the worktree (`data/` is gitignored) and never go into git, the report or your messages. The
  report holds counts, article ids and keys only.
- Keys: `DS_API_KEY` and `JEV_API_KEY` from the main folder's `.env`. Never print, log or commit them.
- Budget: every new call goes through a `PilotJournal` and a guard that refuses a dispatch when the
  new spend of this pilot plus the call's reservation would exceed $0.30. On the cap: stop, keep
  what is done, report partial results. Any `PilotStopped` stops the run: report it, do not work
  around it.

## Steps

1. Worktree from `origin/master`:
   `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER fetch origin`
   `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER worktree add /Users/vyacheslavorlovskiy/GitHub/AI_PARSER-wt-summary-grounding -b docs/summary-grounding-pilot-20261023 origin/master`
   Python: `PYTHONPATH=src ../AI_PARSER/venv1/bin/python` from the worktree root.
   `mkdir -p -m 700 data/summary-grounding-pilot`. Read-only inputs from the earlier pilots:
   `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-wt-jev-entailment/data/jev-entailment-pilot/` and
   `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-wt-jev-repair/data/jev-repair-pilot/`
   (`articles.json`, `run_repair.py`). Do not modify them.
2. Read: `grounded_summary`, `summary_request`, `SUMMARY_INSTRUCTIONS`, `parse_summary`,
   `review_summary`, `salvage_supported_facts`, the per-article enrichment in `enrichment.py`, and
   pilot 2's `run_repair.py` (journal replay, budget guard, Jev check, how outcomes are counted).
3. Sets (one row per article, content-hash checked as in pilot 2):
   - A, "detail outside the quote": the 131 articles of pilot 2 (`articles.json`, already exported).
     Use a random 70 of them (fixed seed).
   - B, control: 30 random articles whose first full-summary review both DeepSeek and Jev accepted
     in pilot 1. Export them read-only as pilot 2 did (one `SELECT` by
     `enrichment_provenance -> summary_review -> request_key`). If the permission classifier
     blocks the export, ask the owner to run your exact command with the `!` prefix in your
     session; do not look for another route. If the owner does not answer, go on with set A only
     and say so.
4. Variants of the attempt-0 instruction text (patch in the script's namespace, not in `src/`):
   - `current`: today's text. Do not call the provider for it: its outcome is already known from
     the journals (accepted by DeepSeek; Jev verdict from pilot 1).
   - `V1`: today's text plus: "Every name, number, role, product and attribution in a sentence
     must appear in its own quote. When you attribute a claim, choose a quote that names who makes
     it; if no such quote exists, state the claim without naming a speaker."
   - `V2`: V1, and drop "Attribute vendor claims" from the attempt-0 text (keep "preserve
     uncertainty").
   Keep the repair texts (attempts 1+) and `SUMMARY_INSTRUCTIONS` unchanged.
5. Run per article and variant the real pipeline (`grounded_summary` with the unchanged DeepSeek
   review; new journals per variant so nothing replays across variants). Then ask Jev (pilot 1
   questions, unchanged) on the final facts. Record: outcome (full / partial / held), DeepSeek
   accepted on the first review (yes/no), Jev P on final facts, summary words, calls, micro-USD.
   Order: V1 on all articles first, then V2; if the cap is near, report what is done.
6. Blind judge: for each variant, 25 random final summaries from set A and 10 from set B (facts
   only, no model verdicts, variants shuffled): supported / not supported, and informative (yes:
   says what happened / no: vague). Name your model. If you are a DeepSeek model, skip this and
   list the keys.
7. Report `docs/report-summary-grounding-pilot-<YYYY-MM-DD>.md`: sets and counts, per variant:
   held share and partial share (must not get worse than `current` on set B), first-review
   DeepSeek acceptance, Jev reject share at 0.5 and at 0.6 (Jev varies by up to 0.09 on the same
   input), judge supported and informative shares, mean words, cost per article and the weekly
   cost change versus today. End with one recommendation: the variant to ship (with its exact
   text), or none, with the numbers. Under "Questions" list anything you decided yourself, one line
   each.
8. Docs-only PR (no full gate; say so in the PR body):
   `git add docs/report-summary-grounding-pilot-<date>.md`
   `git commit` with message `docs(pilot): summary prompt variants that keep details in the quote`,
   a blank line, a one-line summary, a blank line and
   `Co-Authored-By: <your model name> <noreply@anthropic.com>` (use your real model name).
   `git push -u origin docs/summary-grounding-pilot-20261023`
   `gh pr create --base master --title "docs(pilot): summary prompt variants that keep details in the quote" --body "<summary, recommendation, spend; Docs-only: full gate not run>"`
   Do not merge.

## Report back

PR link; set sizes; per variant: held / partial, Jev reject share, judge supported / informative,
cost; the recommendation; anything that stopped you or that you skipped.
