# Prompt: offline pilot 2, do Jev-rejected summaries survive a repair (2026-10-23)

You work in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. Read `AGENTS.md` first. The owner writes
Russian and takes part minimally; report to the session that sent you this prompt.

## Why

Pilot 1 (`docs/report-jev-entailment-pilot-2026-10-23.md`, PR #99) found that Jev rejects 258 of the
465 summaries DeepSeek accepts, and a blind judge sided with Jev on 43-54 of 80 disagreements: about
a third of published summaries carry a detail that is not in their paired quote. A stricter gate
(publish only what DeepSeek AND Jev accept) would send about 131 articles a week into repair.
Question: how many of them survive the repair (full or partial summary) and how many are held, and
what does it cost? Offline only; nothing changes on prod or on the site.

Owner approved the spend: hard cap $0.20 for all new calls (DeepSeek + Jev) in this pilot.

## Hard rules

- Prod (`ssh ai-news`) is read-only: `scp` from the server and `SELECT` only. No writes, no restarts.
- No changes under `src/` or `tests/`. Scripts and private data (article text, quotes, summaries,
  provider responses) stay in `data/jev-repair-pilot/` of the worktree (`data/` is gitignored) and
  never go into git, the report or your messages. The report holds counts, article ids and keys.
- Keys: `DS_API_KEY` and `JEV_API_KEY` from the main folder's `.env`. Never print, log or commit them.
- Budget: every new call goes through a `PilotJournal` and a guard that refuses a dispatch when the
  new spend of this pilot plus the call's reservation would exceed $0.20 (replayed saved responses
  are free). On the cap: stop, keep what is done, report partial results. Any `PilotStopped` stops
  the run: report it, do not work around it.

## Steps

1. Worktree from `origin/master`:
   `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER fetch origin`
   `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER worktree add /Users/vyacheslavorlovskiy/GitHub/AI_PARSER-wt-jev-repair -b docs/jev-repair-pilot-20261023 origin/master`
   Python: `PYTHONPATH=src ../AI_PARSER/venv1/bin/python` from the worktree root.
   `mkdir -p -m 700 data/jev-repair-pilot`. Pilot 1 data is in
   `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-wt-jev-entailment/data/jev-entailment-pilot/` (read
   only: `pairs.json`, `jev-results.json`, `analyze.py`, `journals/`). Do not modify it.
2. Read before writing code: `grounded_summary`, `review_summary`, `salvage_supported_facts`,
   `summary_request`, `parse_summary`, the per-article enrichment (`enrichment.py` ~300-358,
   `enrichment_provenance` with `summary`, `summary_review`, `source_content_hash`,
   `material_type`), `PilotJournal.call`/`_attempt`, and pilot 1's `analyze.py` and
   `ask_jev.py` (Jev request shape and the two questions; reuse them unchanged).
3. The set: articles whose first full-summary review DeepSeek accepted and Jev rejected
   (t = 0.5), as pilot 1's `analyze.py` counts the "repairs added" chains. Write their review keys
   to `data/jev-repair-pilot/keys.txt`; report the count (expected about 131).
4. Article rows (read-only export). Published articles store the accepted review key in
   `enrichment_provenance -> summary_review -> request_key`. Export `id`, `title`, `content`,
   `enrichment_provenance` (and any other column `summary_request`/`source_state` needs) of the
   articles whose key is in `keys.txt`, from `ai-news-db` with one `SELECT ... ` inside
   `docker exec ai-news-db psql -U ainews -d ainews` into `data/jev-repair-pilot/articles.json`.
   Keep a row only if `fingerprint(content) == provenance.source_content_hash`; count the rest.
   If the permission classifier blocks the export (it blocked pilot 1), stop and ask the owner to
   run your exact command with the `!` prefix in your session; do not look for another route.
5. Replay journals: copy pilot 1's `journals/<day>/journal.sqlite3` to
   `data/jev-repair-pilot/journals/<day>/` and open each copy with the same identity, caps and
   transport settings `enrichment.py` uses, so attempt-1 summaries and DeepSeek reviews replay
   from saved responses at no cost. Check on 3 articles that attempt 1 replays without a dispatch
   before going on.
6. Stricter gate, simulated in your script (patch `review_summary` in the script's namespace,
   not in `src/`): the review is the DeepSeek review (unchanged) and then, only if DeepSeek
   accepted, the Jev check on the same `facts` (pilot 1 questions, accept when
   min(P) >= 0.5). Accepted = both accept. Reason passed on: DeepSeek's reason when DeepSeek
   rejected, otherwise empty (then the existing code takes its quote-repair path). Jev calls go
   through a separate `PilotJournal` (`data/jev-repair-pilot/jev-journal.sqlite3`, identity
   `{"version": "jev-repair-pilot-1"}`). Run `grounded_summary` per article in a random order
   (fixed seed); `comparison` = `material_type == "Comparison"`.
7. Outcome per article: `full` (a repaired summary passes both), `partial` (salvage keeps some
   facts), `held` (`SummaryHeld`); with new DeepSeek and Jev micro-USD and calls.
8. Blind check of quality: judge 30 random `full`/`partial` results yourself (facts only, no
   model verdicts): supported / not supported. Name your model. If you are a DeepSeek model,
   skip this and list the keys.
9. Report `docs/report-jev-repair-pilot-<YYYY-MM-DD>.md`: set size, rows kept after the hash check,
   replay check, processed count (all or partial at the cap), outcomes (full / partial / held,
   counts and shares), spend (DeepSeek, Jev, per article), judge result, and the weekly effect of
   the stricter gate on these 7 days: articles held per week out of all published, extra cost per
   week. End with one recommendation for the owner: introduce the stricter gate (yes/no), with the
   numbers that support it. Under "Questions" list anything you decided yourself, one line each.
10. Docs-only PR (no full gate; say so in the PR body):
    `git add docs/report-jev-repair-pilot-<date>.md`
    `git commit` with message `docs(pilot): Jev-rejected summaries after repair, offline results`,
    a blank line, a one-line summary, a blank line and
    `Co-Authored-By: <your model name> <noreply@anthropic.com>` (use your real model name).
    `git push -u origin docs/jev-repair-pilot-20261023`
    `gh pr create --base master --title "docs(pilot): Jev-rejected summaries after repair" --body "<summary, recommendation, spend; Docs-only: full gate not run>"`
    Do not merge.

## Report back

PR link; set size and rows kept; processed count; full / partial / held; spend (DeepSeek, Jev);
judge result in one line; the recommendation; anything that stopped you or that you skipped.
