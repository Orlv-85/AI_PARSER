# Report: offline pilot 3, summary prompt that keeps every detail inside its quote (2026-10-24)

Prompt: `docs/prompt-summary-grounding-pilot-2026-10-23.md`. Follows pilots 1 and 2
(`docs/report-jev-entailment-pilot-2026-10-23.md`, `docs/report-jev-repair-pilot-2026-10-23.md`).
Executor: Claude Opus 5.5 (`claude-opus-5-5`). Offline only: nothing changed on prod, on the site,
in `src/` or in `tests/`.

## Sets

- A, "detail outside the quote": 70 of pilot 2's 131 articles (random, seed 20261023). Rows from
  pilot 2's `articles.json`. **70 of 70 kept** after the `fingerprint(content) ==
  source_content_hash` check.
- B, control: 30 of the 91 articles whose first full-summary review both DeepSeek and Jev (t = 0.5)
  accepted in pilot 1 (random, seed 20261024; same article grouping as pilot 2's `make_set.py`).
  One read-only `SELECT` on `ai-news-db` by `enrichment_provenance -> summary_review ->
  request_key`, run in a read-only transaction. 30 of 30 exported, **30 of 30 kept** after the hash
  check.
- Order: one shuffle of all 100 (seed 20261025), the same for both variants.

## Run

- Variants patch only the attempt-0 text. The DeepSeek journal wrapper replaces it in place, so
  `grounded_summary`'s request key matches the sent body. A check before any call confirmed the
  text in `src/` is exactly today's and appears once. The repair texts (attempts 1+),
  `SUMMARY_INSTRUCTIONS` and the DeepSeek review are unchanged. Every article had exactly one
  attempt-0 patch (V1 100/100, V2 82/82).
  - `current`: today's text, no calls. Outcome from the journals: DeepSeek accepted the first
    review for every article, by how the sets were built. Jev P from pilot 1.
  - `V1`: today's text plus "Every name, number, role, product and attribution in a sentence must
    appear in its own quote. When you attribute a claim, choose a quote that names who makes it;
    if no such quote exists, state the claim without naming a speaker."
  - `V2`: V1 with "Attribute vendor claims and preserve uncertainty." replaced by "Preserve
    uncertainty."
- Each variant ran in new, empty journals (one DeepSeek, one Jev), with prod's version, transport
  review reason and retry delays, so nothing replayed from prod or across variants. Jev then got
  pilot 1's two questions, unchanged, on the final facts (full or partial). Jev was not a gate.
- Guard: a dispatch is refused when this pilot's spend plus the call's reservation would exceed
  $0.30. V1 ran on all 100 first, then V2.
- **V2 stopped at the cap (`PilotStopped: pilot3_budget_cap`) after 82 of 100 articles (A 57,
  B 25).** The 18 not processed are the last 18 in the fixed order. V2 numbers below are on those
  82.

## Results

Jev reject shares are over articles with final facts (held excluded). "First review" means
DeepSeek accepted the attempt-0 summary. Cost is DeepSeek only (the prod pipeline); this pilot's Jev
checks cost a further ~25 micro-USD per article.

Set A (detail outside the quote):

| | current | V1 | V2 |
|---|---|---|---|
| articles | 70 | 70 | 57 |
| full / partial / held | 100% / 0% / 0% | 86% / 10% / 4% | 72% / 25% / 4% |
| DeepSeek accepts first review | 100% | 77% | 65% |
| Jev reject at 0.5 | 70/70 (100%) | 43/67 (64%) | 30/55 (55%) |
| Jev reject at 0.6 | 70/70 (100%) | 47/67 (70%) | 33/55 (60%) |
| judge supported | 3/25 | 11/25 | 13/25 |
| judge informative | 25/25 | 23/25 | 23/25 |
| mean words | 34.1 | 35.4 | 37.3 |
| DeepSeek micro-USD per article | 1340 | 1579 | 1808 |

Set B (control, both reviewers accepted today):

| | current | V1 | V2 |
|---|---|---|---|
| articles | 30 | 30 | 25 |
| full / partial / held | 100% / 0% / 0% | 90% / 7% / 3% | 92% / 8% / 0% |
| DeepSeek accepts first review | 100% | 83% | 84% |
| Jev reject at 0.5 | 0/30 (0%) | 6/29 (21%) | 5/25 (20%) |
| Jev reject at 0.6 | 4/30 (13%) | 8/29 (28%) | 9/25 (36%) |
| judge supported | 10/10 | 9/10 | 7/10 |
| judge informative | 10/10 | 10/10 | 10/10 |
| mean words | 29.9 | 35.9 | 33.0 |
| DeepSeek micro-USD per article | 1081 | 1254 | 1297 |

- Held and partial reasons: V1 `summary_length_limit` 3, `summary_not_entailed_or_not_english` 4,
  `Unsupported summary quote` 1; V2 2 and 2. Partial (kept/dropped facts): V1 A 2/1: 2, 1/1: 4,
  1/2: 1, B 2/1: 1, 1/2: 1; V2 A 2/1: 6, 1/1: 4, 1/2: 3, 3/0: 1, B 2/1: 1, 1/1: 1.
- Baseline bias: both `current` Jev columns are one reading that was used to select the set. For A
  this does not explain the drop: pilot 2 asked Jev again about the same original facts, and still
  rejected 70 of 70 at 0.5. For B there is no second reading, so part of B's 0% to ~20% could be Jev
  noise. But 7 of the 8 V1 B articles under 0.6 are new text, and Jev dropped from 0.60-0.82 to
  0.12-0.33 on 6 of them. Jev's known variation is up to 0.09.
- The same bias holds for B's outcomes. Every B article had full with `current` by construction. A
  fresh run of today's text on B was not done (the prompt says no calls for `current`), so the
  noise floor of partial and held on B is unknown.
- 8 of 100 V1 final summaries are identical to today's (same sentences and quotes).

## Blind judge

Judge: Claude Opus 5.5. Per variant (`current` included as a baseline), 25 random final summaries
from set A and 10 from set B, 105 in all (seed 20261026), shuffled across variants, facts only, no
model verdicts. Rule as in pilot 2: unsupported if a sentence adds a detail not in its quote or
drops an attribution. Naming a pronoun's referent ("we", "he", "the company") is allowed; generic
framing ("the vendor says", "the authors") is allowed. A named company, person, employer, product
or version not in the quote counts as an added detail. Informative: the facts say what happened,
not just a general statement.

- Most remaining unsupported V1/V2 sentences still add a named actor or source (a company, a
  person's name or employer, a survey name) with no pronoun in the quote to stand for it. Some add a
  product, version or setting detail. The new instruction is followed only in part.
- The judge's three not-informative calls are all on V1/V2 sentences that state only a caveat or a
  general point.

## Spend

- New DeepSeek: **$0.285** (V1 291 calls $0.148, V2 277 calls $0.137). New Jev: **$0.005** (176
  calls). Total **$0.290** of the $0.30 cap. All calls in state `response`, none unknown.
- One V2 call ($0.0016) belongs to the 83rd article, which the cap stopped mid-way. It is not in the
  82 results.

## Weekly cost change (these 7 days)

Per week in pilot 1's journals: 131 articles of A's kind, 91 of B's kind, and about 205 that
DeepSeek rejected at the first review (not sampled here). Today's DeepSeek spend on the first two
groups is about $0.27 per week.

- V1: +239 micro-USD per A article, +173 per B article: about **+$0.05 per week** (+17%).
- V2: +468 and +216: about **+$0.08 per week** (+30%).
- The change for the 205 DeepSeek-rejected articles is not measured.

## Scripts

Private, in `data/summary-grounding-pilot/` of the worktree (not in git):

| script | sha256 |
|---|---|
| `make_sets.py` (step 3) | `da1438f1a7b76d8307c08519455e0f943770de5dbc43050008fe9166a5c2fbd8` |
| `run_variants.py` (step 5) | `685a87a02d56b993da3c25c2d49a612b324e97faafa3b19e036dcece6fcdb377` |
| `judge_sample.py` (step 6) | `245c1c4e70309dad642cb6a07712c60cdf37484170a2a6c922750bd203bbc321` |
| `summarize.py` (step 7) | `691ae202a928b222f1576935fb6ab92607b39df8d27f4e09c4b02dffd2a5d692` |

Article ids with outcomes are in `results-V1.json` and `results-V2.json`, and judge items in
`judge-key.json` / `judge-labels.txt`, in the same folder.

## Recommendation

**Ship none yet.** Neither variant passes the prompt's gate, which says set B must not get worse
than `current`:

- V1 on B: 3% held and 7% partial (0% / 0% today), Jev reject 21% (0%), judge 9/10 (10/10).
- V2 on B: 0% held but 8% partial, Jev reject 20%, judge 7/10.

What the variants do achieve, on set A:

- V1 raises judge-supported from 3/25 to 11/25 and cuts Jev rejects from 100% to 64%, at +$0.05
  per week.
- V2 does a little more on A (13/25, 55%), but it moves 25% of A to partial, does worse on B (judge
  7/10) and costs more. Dropping "Attribute vendor claims" did not help.

V1 is the better candidate. Before shipping it, measure the noise floor: run today's text with
fresh calls on set B, about $0.04, to see whether B's 10% partial and held is the prompt or chance.

## Questions

- Decided (agent): the set B export ran directly over `ssh ai-news` in a read-only transaction; the
  classifier did not block it.
- Decided (agent): each variant used new, empty journals, so its repairs did not replay prod's
  saved responses. It runs on prod's identity version and transport settings.
- Decided (agent): Jev caps on the pilot journals are `jev` 0.299999 / `deepseek` 0.000001 (and
  the reverse for the DeepSeek journals), because `PilotJournal` rejects 0. The $0.30 guard covers
  all four journals.
- Decided (agent): a 3-article V1 run went first to check the cost. It is included in the 100 and
  in the spend.
- Decided (agent): the blind judge also scored `current` (35 items, no calls), to give a baseline
  under the same rule and the same judge.
- Decided (agent): the judge counts a named actor that is in neither the quote nor a pronoun as
  unsupported. This is stricter than the DeepSeek review, and it is the defect this pilot targets.
- Decided (agent): the set A baseline was checked against pilot 2's second Jev reading (70/70 still
  rejected); B has no second reading.
- Owner (product, yes/no): ship V1 now and accept up to ~10% of today's clean summaries becoming
  partial or held, in exchange for A's 3/25 → 11/25? Recommendation: no, measure B's noise floor
  first (~$0.04).
