# Paid pilot checkpoint: 21 of 80 records

Historical checkpoint. The user subsequently authorised continuation, and the
pilot completed all 80 records. See the
[final pilot results](reenrich-pilot-results-2026-10-11.md).

The user explicitly confirmed: "Да, $1.50: JEV $0.25 / DeepSeek $1.25".
These are cumulative pilot-only caps. No mass budget is approved.
The prepared pilot ran once against the existing private source cache and
stopped protectively on an incomplete DeepSeek response. It is not complete.

| Result | Count |
| --- | ---: |
| Frozen pilot records | 80 |
| JEV requests / assessed records | 21 |
| Accepted / reject candidates / unresolved | 4 / 2 / 15 |
| Remaining unassessed | 59 |
| DeepSeek requests | 4 |
| Complete summaries passing literal quote checks | 3 |
| Incomplete summary responses retained | 1 |
| Comparison records identified | 1 |
| Accepted records requiring boundary review | 3 |
| Repeat paid requests / new source downloads | 0 / 0 |
| Production writes / deleted records | 0 / 0 |

Both reject candidates were non-AI results passing the existing conservative
cleanup guardrails; these are diagnostic candidates, not authorised deletions
or changes to the ordinary admission ledger. The four accepts yielded one
AI Applications topic, one QA & Observability topic and two unclassified topics.
Every assessed record so far is in the fresh unresolved cohort. None of the
28 previously accepted controls has been reached. This incomplete coverage
does not support an accuracy or taxonomy-quality conclusion.

## Stop reason and costs

The fourth DeepSeek response reported `finish_reason: length` and exactly
300 completion tokens. The validator rejected it as an incomplete summary,
retained the full response privately, and stopped all further dispatches.
This is an output-size/format problem, not budget exhaustion or unknown billing.
No attempt was silently retried. All 25 calls returned valid usage; there are
zero unknown-usage calls. Model IDs matched the requested versions/aliases.

| Usage-priced amount | JEV | DeepSeek | Total |
| --- | ---: | ---: | ---: |
| Conservative journal dollars | $0.002459 | $0.003749 | $0.006208 |
| Input tokens | 58,295 | 9,278 | |
| Output tokens | 4,972 (free) | 803 | |

These are token-based amounts rounded up per request, using the published
[JEV rate](https://docs.typesafe.ai/models) and DeepSeek's
[peak/cache-miss rates](https://api-docs.deepseek.com/quick_start/pricing/).
They are not a provider invoice; off-peak/cache discounts may reduce the actual
charge. The failed summary's usage is included. The remaining approved headroom
is $1.493792 total, subject to the separate provider limits. There was no new
top-up or unrelated provider operation.

## Retained artifacts and next checkpoint

Everything remains inside `tmp/reenrich-2026-10-11`, with files 0600 and the
run directory 0700. Source text and provider responses were not printed into
Codex context, public reports, logs or Git.

| Private artifact | SHA-256 |
| --- | --- |
| `pilot-report.json` | `a4580714b140597c5a0d55b0ce2c8fd9cc3c3a27ce5ecaa23b4de66c1514fe6c` |
| `pilot-usage.json` | `bcb5e00e66a0cd4b3b4ac2b5426fa815900d6fe75200a675afd808c70067ac6f` |
| `pilot-results.json` | `695d0925e35e35647438666d107255fab8da20b30582bed729c1271346053f3a` |
| `pilot-budget-approval.json` | `0cfa325341f707db95c6d2de914128309bc7e7aea53e3ca96b079dba3d5f503e` |

The frozen pilot plan and source cache hashes are unchanged; see the
[preparation report](reenrich-pilot-preparation-2026-10-11.md). The response/usage
journal `pilot-journal.sqlite3` prevents repayment of completed calls. An
unchanged rerun stops on the recorded incomplete response. Do not delete/reset
the journal, replace the paid plan, redownload sources or regenerate summaries
for the three completed records.

Recovery should shorten the structured summary/quote/product payload or revise
the output cap, explicitly version that request change and record the known
failed attempt. Preserve the original paid plan and cumulative provider/total
spend; any deliberate replacement request must remain within the confirmed
pilot budget. There is no reason to ask for the same $1.50 approval again.
Unknown outcomes must still never be automatically retried. This checkpoint
stops before recovery, completing the other 59 assessments, or mass processing.

Validation: 85 scoped synthetic/provider regression tests passed; Ruff passed
for src/tests and the re-enrichment scripts; mypy passed for 143 source files;
scoped pylint passed at 10.00/10. Full repo pytest and full `make lint` were not
run; no commit/push, schema change, production apply or PostgreSQL rehearsal
was performed. Weekly stays off; retention and size thresholds were unchanged.
