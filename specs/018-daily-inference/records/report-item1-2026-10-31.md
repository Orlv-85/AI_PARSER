# Report: spec 018 item 1, Jev world_change questions (2026-10-31)

Written by the implementing session (PR #155); saved by the coordinator because the subagent could
not write report files.

## Run

- 260 digest articles of 2026-10-24, -25, -28, -29, -30 (exported read-only from prod), one
  separate Jev request each (`WORLD_CHANGE_VERSION = "world-change-1"`).
- 0 failures, 730,576 input tokens, $0.031 (cap $0.20). No DeepSeek calls.
- Reference labels by a separate session that did not see Jev's answers
  (`prompt-item1-labels-2026-10-31.md`); it judged title plus about 400 characters of text.
- The questions were not tuned on the labels.

## Agreement with the labels

| Question | Agreement |
| --- | --- |
| world_change | 180/260 = 0.692 |
| area | 197/260 = 0.758 |
| actor | 179/260 = 0.688 |
| harm_to_people (p >= 0.5) | 250/260 |

`world_change` distribution, Jev vs labels: added 56 vs 63, changed 47 vs 49, issue 30 vs 27,
limit 10 vs 8, none 117 vs 113. Per day: 10/15, 12/19, 54/75, 47/68, 57/83.

Confusion (rows labels, columns Jev):

| | added | changed | issue | limit | none |
| --- | --- | --- | --- | --- | --- |
| added | 43 | 3 | 0 | 0 | 17 |
| changed | 3 | 27 | 1 | 0 | 18 |
| issue | 0 | 1 | 23 | 0 | 3 |
| limit | 0 | 0 | 0 | 8 | 0 |
| none | 10 | 16 | 6 | 2 | 79 |

`issue` and `limit` are reliable; disagreements sit on the border with `none`.

Agreement by Jev confidence:

| Jev confidence | Agreement | n |
| --- | --- | --- |
| below 0.6 | 0.46 | 82 |
| 0.6-0.7 | 0.58 | 26 |
| 0.7-0.8 | 0.74 | 34 |
| 0.8-0.9 | 0.82 | 44 |
| 0.9 and above | 0.89 | 74 |

Stories shown (answer not `none`) by threshold:

| Threshold | Shown | Labels also non-none | Exact label | Share of 147 labelled non-none |
| --- | --- | --- | --- | --- |
| 0.5 | 106 | 90 | 85 | 0.61 |
| 0.6 | 90 | 79 | 75 | 0.54 |
| 0.7 | 80 | 70 | 68 | 0.48 |
| 0.8 | 62 | 56 | 55 | 0.38 |
| 0.9 | 37 | 34 | 34 | 0.23 |

Proposed FR-003 threshold: **0.7** (about 16 candidates per day before caps; 88% also non-`none`
by the labels). Harm stories hidden at `harm_to_people` p >= 0.7 (labels: 2 yes; Jev flags 5 at
0.7, both labelled ones among them). One sample only: re-check after the first preview weeks.

## Five disagreements

1. "Anthropic's financials are surprisingly strong": Jev none (1.00), label changed (S-1 financials
   read as industry-internal).
2. "Google announces Gemini 4 Carbon ... you can't use ...": Jev none (0.99), label added.
3. "Drama 3 just leveled up": Jev none (0.90), label added (newsletter blurb).
4. "The AI Skills That Actually Show Up in Job Postings Right Now": Jev changed (0.91), label none.
5. "How the UK Amazon Quick User Group grew in 2026": Jev changed (0.87), label none.

Possible sharpening of `none` (announced model = `added`; advice and opinion = `none`) needs a new
version and a rerun (about $0.03); not done.

## Decided by the implementing session

- Journal per day and cap in `data/bulletin/<day>/journal-<version>-<cap>.sqlite3` (the journal
  identity includes the caps).
- `cost_usd` in the command summary is the journal total for that day and cap.
- `harm_to_people` stored as a probability; the bulletin picks the threshold.
- One invalid answer of the four drops the whole assessment.
- Transport timeout 60 s (requests are larger than the 5 s `jev_timeout_seconds` assumes).
- Default cap of `bulletin assess`: $0.05 (FR-012).
- Area criteria worded from `voice.md`.
