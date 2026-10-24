# Report: offline pilot 2, do Jev-rejected summaries survive a repair (2026-10-23)

Prompt: `docs/prompt-jev-repair-pilot-2026-10-23.md`. Follows pilot 1
(`docs/report-jev-entailment-pilot-2026-10-23.md`). Executor: Claude Opus 5.5 (`claude-opus-5-5`).
Offline only: nothing changed on prod, on the site, in `src/` or in `tests/`.

## Set and inputs

- Set: articles whose first full-summary review DeepSeek accepted and Jev rejected (t = 0.5),
  counted as pilot 1 counts its "repairs added". Result: **131** (keys in `keys.txt`).
- Article rows: one read-only `SELECT` on `ai-news-db`, run by the owner with `!` after the
  permission classifier blocked it. 131 of 131 rows exported, **131 kept** after the
  `fingerprint(content) == source_content_hash` check, 0 dropped.
- Replay check, before any paid call, on all 131: the reviewed summary and its DeepSeek review are
  saved responses with the expected review key. For 89 the reviewed summary was attempt 0. For 42
  attempt 0 was unparsable or over the length limit, and the reviewed summary was the quote
  repair. In the run, all 131 replayed these steps with no DeepSeek dispatch; the first new call
  was always Jev.

## Run

- The stricter gate was simulated by patching `review_summary` in the script namespace only. The
  DeepSeek review is unchanged. Only when DeepSeek accepts, Jev checks the same `facts` with pilot
  1's two questions, unchanged; accept when min(P) >= 0.5. Accepted = both accept. On a Jev
  reject the reason is empty, so `grounded_summary` takes its quote-repair path. Salvage reviews
  use the same gate.
- Day journals were opened with prod's identity, caps and transport settings. Jev went to
  `jev-journal.sqlite3` (identity `{"version": "jev-repair-pilot-1"}`). A guard refused any
  dispatch that would take this pilot's new spend over $0.20. Order: random, seed 20261023.
- Processed: **131 of 131**. No `PilotStopped`, cap not reached.

## Outcomes

| outcome | articles | share |
|---|---|---|
| full (repaired summary passes both) | 7 | 5% |
| partial (salvage keeps some facts) | 50 | 38% |
| held (`SummaryHeld`) | 74 | 56% |

- In 1 of the 7 full cases, Jev scored the original facts at 0.50 on this run, against a score
  under 0.5 in pilot 1: Jev's answer on the same input varies near the threshold. The other 6
  passed after a new summary.
- Partial (kept/dropped facts): 2/1: 18, 1/2: 18, 1/1: 13, 3/0: 1.
- Per day (full/partial/held): 10-16 1/6/6, 10-17 0/3/0, 10-18 0/2/4, 10-19 2/12/12,
  10-20 0/7/13, 10-21 3/8/17, 10-22 1/12/22.

## Spend

- New DeepSeek: **$0.106** (420 calls). New Jev: **$0.010** (362 calls). Total **$0.116** of the
  $0.20 cap.
- Per article: mean 884 micro-USD. By outcome: full $0.007, partial $0.051, held $0.059.

## Blind check of quality

Judge: Claude Opus 5.5. Sample: 30 random full/partial results (seed 20261024), facts only, no
model verdicts. Same rule as pilot 1: unsupported if the sentence adds a detail not in its quote or
drops an attribution; naming a pronoun's referent is allowed.

- **30 of 30 supported.**

## Weekly effect of the stricter gate (these 7 days)

- Articles published from the 7 day journals: 376. This is an estimate from the journals: articles
  with any DeepSeek-accepted review. It excludes articles reused from earlier runs.
- Held by the stricter gate: **74 of 376 (about 20%) per week**. A further 50 published articles
  get a shorter, partial summary.
- This is a lower bound. The gate would also apply to the repairs of the 205 articles DeepSeek
  rejected first, and those were not simulated.
- Extra cost: about **$0.12 per week**, which is $0.116 in repairs for this set plus about $0.01 of
  Jev checks on the other DeepSeek-accepted reviews.

## Scripts

Private, in `data/jev-repair-pilot/` of the worktree (not in git):

| script | sha256 |
|---|---|
| `make_set.py` (step 3) | `fe2ead1e349ce08e33248e97984166f75d04b3d4dfdb7e0d6c2692dbd75f8bc4` |
| `run_repair.py` (steps 4-7) | `1c19141af7ded006b3dfada36bf3bf51b05db099700ba219116d2ba16078e7de` |
| `summarize.py` (steps 7-8) | `3a5d729e52f0468126baf9c592da41012ff281bf094c876391f44b2fa371f92d` |
| `count_published.py` (step 9) | `4659487e48afb4e9a0307ba70b5fe34938e31ffab0c33698369b6ed56decd9f7` |

Article ids with outcomes are in `results.json` in the same folder.

## Recommendation

**Do not introduce the stricter gate (no).**

- It removes about 20% of the week's published articles: 74 of 376, held. It also cuts 50 more
  summaries down to partial ones.
- What it fixes is limited. In pilot 1 the extra Jev rejections were mostly details that are not
  in the paired quote. They may appear elsewhere in the article; the judge saw only the quote.
- Cost is not the issue (about $0.12 per week); coverage is. Only 7 of 131 got a full repaired
  summary.

## Questions

- Decided (agent): the article export was blocked by the permission classifier again. As the
  prompt says, the owner ran the exact command with `!`; the session found no other route.
- Decided (agent): the replay check follows prod's path. When attempt 0 is unparsable or over the
  length limit, the reviewed summary is the quote repair (42 articles), and the 10-19 transport
  retry chain is read through `PilotJournal._attempt`.
- Decided (agent): Jev budget caps `jev` = 0.199999, `deepseek` = 0.000001, `total` = 0.2, because
  `PilotJournal` rejects 0 and requires jev + deepseek <= total. The $0.20 pilot guard covers both
  providers.
- Decided (agent): a 3-article run went first, to confirm replay and cost. It is included in the
  131 and in the spend.
- Decided (agent): "published" for the weekly share is estimated from the journals (376), not from
  the DB.
- Decided (agent): the Jev variation near the threshold (1 case) is reported, not corrected.
