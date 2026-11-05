# FR-022 summary: 2026-11-02..04

Reviewed 21 stored preview stories against the local source packets rebuilt on 2026-11-05.
All three days used bulletin-writer-3, model deepseek-flash.
Scope: published headline, site, Telegram and gloss fields, including title fallback,
selection, day headline and drop diagnostics. No code or prompt changes were made.

| Bulletin date | Model / title | ok | minor | wrong | Dropped |
| --- | --- | --- | --- | --- | --- |
| [2026-11-02](review-2026-11-02.md) | 7 / 0 | 1 | 5 | 1 | 24 |
| [2026-11-03](review-2026-11-03.md) | 7 / 0 | 1 | 4 | 2 | 28 |
| [2026-11-04](review-2026-11-04.md) | 6 / 1 | 4 | 2 | 1 | 18 |
| Total | 20 / 1 | 6 | 11 | 4 | 70 |

Each story is counted once at its highest severity. Selection concerns and day-headline
findings are additional observations, not extra stories in these counts.

## Meaning errors

- November 2, s1: Circle K's performance headline presents the vendor/customer case-study
  claim as an established outcome, without the attribution required by ER-1.
- November 3, s5: "ahead of US midterms" misdates a report whose source says voting is today.
- November 3, s6: the Apple headline extends the age restriction from dating/romantic
  features to AI companion apps generally.
- November 4, s5: ten states describes all ballot measures considered, not the states in
  which restrictions passed; the headline claims a distribution of wins the source does not establish.

Exact published strings and source passages are in the daily reviews. These are findings
against the supplied packet, not independent verification of the underlying reporting.
The rebuilt texts may differ from those seen at the original call; temporal and missing-evidence
findings should be compared with original call packets if those become available.
That caveat does not supply missing support for the published wording.

## Ranked fixes

Proposals only; no approval, implementation or paid rerun is implied.

1. **F2 -- prompt: Preserve scope and number context.** Carry feature eligibility, trial/rollout
   limits and the population behind every count into headlines and summaries; never convert
   ballot coverage into the geographic distribution of successful votes.
   Evidence: November 3 s3/s6; November 4 s5.
2. **F1 -- prompt: Preserve claimant attribution.** Name the vendor/customer on performance
   claims, including standalone headlines, rather than relying on the source link.
   Evidence: November 2 s1.
3. **F3 -- prompt: Preserve event time.** Distinguish source publication, earlier events,
   present conditions and future plans; anchor relative wording to the bulletin's date.
   Evidence: November 2 s2; November 3 s5.
4. **F4 -- rule: Check coherence after drops, separately for each channel.** Require a retained
   event, identified subject and essential conditions/tradeoffs; otherwise use a complete
   fallback. Do not keep background-only or pronoun-only notes merely because a sentence passed.
   Evidence: November 2 s1/s3/s5/s6/s7; November 3 s6/s7; November 4 s3.
5. **F8 -- rule: Bind the day headline to the ranked story.** Select the FR-004 anchor before
   writing and check headline evidence against that story; preserve material tradeoffs.
   Evidence: November 2 day headline; November 3 cut headline illustrates loss of the tradeoff.
6. **F5 -- rule: Keep only relevant, evidenced glosses.** Omit a gloss when its referent has been
   dropped or its definition is not supported by the packet; distinguish a research model
   instance from its family.
   Evidence: November 2 s5; November 3 s2/s4/s5/s7; November 4 s5.
7. **F6 -- rule: Review relevance and section assignment.** Require a concrete world change
   beyond a capability launch; keep opinion and forecast framing and do not count a forecast
   as a realised incident.
   Evidence: November 3 s1/s3; November 4 s2/s3/s7.
8. **F7 -- prompt: Paraphrase profanity with attribution.** Retain the criticism without
   importing slang into the official register.
   Evidence: November 4 s7.

The 70 drops comprise 59 too_close, 3 quote_not_found, 4 unsupported_name,
2 word_count, 1 long_quote and 1 never_list. These are diagnostic entries, including
headline/gloss failures, not 70 recoverable rejected sentences. The rejected wording is
not supplied. Do not infer false-positive copying checks or recommend weakening ER-9
from these counts. The supported conclusion is that retained notes need a coherence check.

## SC-002 so far

The reviewed sample does **not** meet "no story with distorted meaning": four of 21 stories
are wrong under the requested rubric. It therefore provides no basis to claim SC-002 achieved.

The formal semantic window is the **last seven of the first fourteen published days**,
not these first three days. That final window remains unevaluated; this review does not
prejudge its eventual result. The proposed fixes address the present failures.

All 21 stories have source links in the stored payload and corresponding packet stories.
The packet is not an independent proof of source publication/collection dates or a replay
of the original grounding checks. No fresh grounding audit was run, so the other SC-002
clauses are not newly certified here.

## Review decisions and validation

Decided by this review: one highest-severity verdict per story; title-only output is assessed
as published; unsupported scope counts as wrong even when the asserted outcome might be true.
A valid definition of a dropped entity is minor, not an invented fact. The vendor performance
finding applies ER-1; it does not claim the customer's measurement is false.

Validated all cited source passages as exact substrings of the corresponding supplied article,
preserved published fields with reversible JSON escaping for ASCII, and checked verdict/drop
totals and story coverage. No network, paid calls, sub-agents, code changes, commit, push or gh.
Pytest and repo-wide quality gates were not run: this task only adds review records and forbids
commit/push. Source material outside the worktree was read only.


## Coordinator check (2026-11-05)

The coordinator (Claude) re-read the four `wrong` stories against the packet:

- November 2 s1 (Circle K): agree, `wrong` under ER-1. The headline states the customer's
  internal metric as fact; the source is an AWS case study.
- November 3 s5 (midterms): downgrade to `minor`. The source itself frames the findings as
  "ahead of the midterms" ("Ahead of the midterms, many more of these sites have sprung up");
  only the polling-day lead differs.
- November 3 s6 (Apple): downgrade to `minor`. The headline drops "that engage in sexual or
  romantic content", but the outlet's own title makes the same cut ("Apple restricts dating apps
  and AI companions to users 18 and up").
- November 4 s5 (data centres): downgrade to `minor`. "Across ten states" is broader than
  "38 of 44 measures across 10 states passed", but the meaning (voters backed restrictions in
  that set of states) is not reversed.

Counted after this check: 1 `wrong` (ER-1 attribution), 14 `minor`, 6 `ok`. The fix that matters
most is F1 (attribute company claims in headlines too), then F2 (keep scope qualifiers). F1 and F2
are prompt changes and change what readers see, so they wait for the owner.
