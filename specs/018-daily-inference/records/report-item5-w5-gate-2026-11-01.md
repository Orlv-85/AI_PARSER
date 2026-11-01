# Report: spec 018 item 5, W5 gate run on one real GDELT day (2026-11-01)

Background agent (model sonnet), prompt `prompt-item5-w5-gate-2026-11-01.md`; saved by the
coordinator. Base `origin/master` e15e3d3 (PR #188). One real `world screen` run, no rerun; temp
SQLite in the scratchpad; only `JEV_API_KEY` exported. Worktree, database, journal and `data/`
deleted afterwards.

## Commands

`alembic upgrade head`; `world collect --date 2026-10-31` (after a `--max-files 2` smoke run);
`world screen --date 2026-10-31 --dry-run`; `world screen --date 2026-10-31` once. The CLI module
has no `__main__` guard: run as `python -c "from app.cli.main import app; app()" ...`.

## Collect (2026-10-31)

Full run: files 190 (2 skipped, done by the smoke run), missing 0, partial false, rows 203,250,
matched 3,035, kept 2,247, new 2,238, repeats 9. Database: 2,256 candidates in 1,842 clusters.
About 4 minutes.

## Screen

- Dry run: `would_screen 1842`, `would_follow 414`, `would_assess 0`.
- Real: requests 1,842, screened 2,256, in 1,521, out 735, failed 0, not_attempted 0, assessed 0,
  `awaiting_text 100` (step B needs W6 text).
- Usage: 1,842 calls, all `response`, unknown 0, `total_committed_usd` 0.033536; input tokens
  775,105, output 42,366.

| Item | Plan | Measured |
| --- | --- | --- |
| Input tokens per request | about 300 | mean 421, p50 418, p95 452, max 612 |
| Output tokens per request | priced 0 | mean 23 |
| Step A cost | $0.03-0.04 for A and B | $0.0335 (34% of the $0.10 cap) |
| Candidates per day | 1,619 | 2,256 (1,842 clusters) |

Title-only state: Jev accepted all 1,842 requests. Late-outlet follow across runs was not exercised
(one run); 414 in-run followers got a state without a request.

## Precision of step A (blind labels)

120 random cluster representatives (`random.seed(20261101)`), labelled from title, domain and
language before Jev results were read; 59 `in`, 61 `out`; one labeller, about 15 borderline.

| Threshold | Kept of 120 | Precision | Recall | `in` lost |
| --- | --- | --- | --- | --- |
| 0.3 | 85 | 0.68 | 0.98 | 1 |
| 0.4 | 73 | 0.77 | 0.95 | 3 |
| **0.5 (current)** | 63 | 0.83 | 0.88 | 7 |
| 0.6 | 59 | 0.86 | 0.86 | 8 |
| 0.7 | 48 | 0.88 | 0.71 | 17 |
| 0.8 | 35 | 0.91 | 0.54 | 27 |
| 0.9 | 13 | 1.00 | 0.22 | 46 |

Recall is among keyword-filtered candidates only. Main error: Jev scores opinion and commentary
"about AI" as in scope (for example "Is AI slipping beyond human control?" 0.87); corporate/B2B
deployments score low (borderline in the labels too).

## Top N

1,180 clusters `screened_in` (64%), 296 with confidence >= 0.9; `WORLD_TOP_N` = 100. Top 20 by
confidence x outlets is mostly on scope (for example "Your writing was flagged as AI. What does
that actually mean?" 0.83 x 80; "Americans open to AI in health care but want humans calling the
shots" 0.96 x 55; "KI-Blitzer in Spanien" 0.81 x 9); 2 of 20 weak (an OpenAI court filing, a data
handbook).

## Conclusions

- `SCREEN_THRESHOLD` stays 0.5 (precision 0.83, recall 0.88); 0.6 is a reasonable later tweak; 0.7+
  loses too many. Ranking for the top 100, not the threshold, is the real filter.
- Cost: step A $0.034 measured; step B for 100 texts estimated $0.007-0.018 by the plan's
  arithmetic, so about $0.04-0.05 a day, under the $0.10 cap. Step B to be measured after W6.
- Confidence is bimodal (peaks near 0.9, 0.8 and 0.1).
