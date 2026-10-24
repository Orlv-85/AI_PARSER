# Prompt: daily summary keeps every detail inside its quote (code change, 2026-10-24)

You work in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. Read `AGENTS.md` first (especially
"Feature Docs Next To Code", "Validation", "Owner And Questions"). The owner writes Russian and
takes part minimally; report to the session that sent you this prompt.

## Why

Pilots 1-3 (`docs/report-jev-entailment-pilot-2026-10-23.md`,
`docs/report-jev-repair-pilot-2026-10-23.md`, `docs/report-summary-grounding-pilot-2026-10-24.md`
with its noise-floor addendum) found that about a third of daily summaries carry a detail (a named
actor, product or number) that is not in their paired quote. Prompt variant V1 raised blind-judged
supported summaries on the affected set from 3/25 to 11/25 and did not hurt the control set beyond
the noise of a fresh run; about +$0.05 per week. The owner approved shipping V1 (2026-10-24).

## Scope

Only the attempt-0 instruction text of `grounded_summary` in `src/app/core/daily/enrichment.py`
(the `if attempt == 0:` block, lines ~234-238), the feature doc, and tests. Not in scope:
`SUMMARY_INSTRUCTIONS` in `reenrich_pilot.py`, the repair texts (attempts 1+), the review, Jev,
`DAILY_VERSION`, `RUBRIC_VERSION`, caps, `reusable`.

## Steps

1. Worktree from `origin/master`:
   `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER fetch origin`
   `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER worktree add /Users/vyacheslavorlovskiy/GitHub/AI_PARSER-wt-summary-details -b fix/summary-quote-details-20261024 origin/master`
   Checks run as `PYTHONPATH=src ../AI_PARSER/venv1/bin/...` from the worktree root.
2. Doc first, `src/app/core/daily/enrichment.md`:
   - Behavior: add a rule: the first summary request asks that every name, number, role, product
     and attribution in a sentence appears in its own quote, and that a claim is attributed only
     to a speaker its quote names; repairs and the review are unchanged; the request's version is
     recorded in `enrichment_provenance` as `summary_prompt`. `Tests:` the tests of step 4.
   - Decisions: "2026-10-24 (owner): the first summary request keeps every detail inside its quote
     (pilots 1-3, `docs/report-summary-grounding-pilot-2026-10-24.md`); a stricter review gate was
     rejected because it held ~20% of the digest."
   - Invariants: unchanged summaries already published are reused as before (`reusable` does not
     depend on the prompt).
3. Code, `src/app/core/daily/enrichment.py`:
   - Add a module constant `SUMMARY_PROMPT_VERSION = "daily-summary-details-1"` next to
     `DAILY_VERSION`.
   - In the `if attempt == 0:` block append, after "Attribute vendor claims and preserve
     uncertainty.", exactly this text (leading space included):
     `" Every name, number, role, product and attribution in a sentence must appear in its own quote. When you attribute a claim, choose a quote that names who makes it; if no such quote exists, state the claim without naming a speaker."`
     Prefix it with the version tag so the request names it, as the repair texts do:
     `" Summary rule " + SUMMARY_PROMPT_VERSION + ":"` immediately before that text.
   - In `enrichment_provenance` (the `encoded({...})` around line 350) add
     `"summary_prompt": SUMMARY_PROMPT_VERSION`.
   - Do not change `DAILY_VERSION`: it is part of the day journal identity, and a change breaks the
     resume of a day whose journal already exists (`Pilot identity or approved budget changed`).
4. Tests, `tests/unit/test_daily_enrichment.py` (follow its fixtures and fake journal):
   - `test_first_summary_request_keeps_details_in_quote`: the attempt-0 DeepSeek body contains
     the rule and `SUMMARY_PROMPT_VERSION`; the attempt-1 bodies (quote repair and entailment
     repair) do not.
   - `test_provenance_records_summary_prompt_version`: an enriched article's provenance has
     `summary_prompt == SUMMARY_PROMPT_VERSION`.
   - `test_reuse_ignores_summary_prompt_version`: an article published with provenance without
     `summary_prompt` is still `reusable`.
   Extend existing tests instead if one already covers the same path; name them in the doc.
5. Checks (all of them, it is a code PR):
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest tests/unit/test_daily_enrichment.py`
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/python scripts/check_code_docs.py` (if it has a CLI;
   otherwise its pytest test)
   `make lint PYTHON=../AI_PARSER/venv1/bin/python`
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest`
   If a check fails for a reason outside this change, read `docs/troubleshooting.md` first and
   report it; do not fix unrelated code.
6. Commit and PR:
   `git add src/app/core/daily/enrichment.py src/app/core/daily/enrichment.md tests/unit/test_daily_enrichment.py`
   Message: `fix(daily): first summary request keeps every detail inside its quote`, a blank line,
   two lines on why (pilots 1-3, owner yes 2026-10-24), a blank line,
   `Co-Authored-By: <your model name> <noreply@anthropic.com>` (use your real model name).
   `git push -u origin fix/summary-quote-details-20261024`
   `gh pr create --base master --title "fix(daily): first summary request keeps every detail inside its quote" --body "<what, why with the pilot numbers, tests, full gate result>"`
   Do not merge and do not tag: merge and deploy need the owner's yes.

## Report back

PR link; diff summary (files, lines); test names; output of every check (pass/fail, counts);
anything you decided yourself, one line each.
