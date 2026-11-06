# World stream, nights 2026-11-02..06: days 2026-11-01..05 (FR-018)

Source: `ai-news world report --date D` for D = 2026-11-01..05, run read-only in `ai-news-app` on
2026-11-05 ~21:30 UTC (v0.1.159). Each report covers the window of `world screen`: GDELT days `D-1`
and `D`, so adjacent windows share a day. Day 2026-11-05 is partial (its night run is 2026-11-06).

## FR-018 numbers

| D | Candidates | Clusters | Screened in / out | No text | Failed | Assessed | added / changed / issue / limit / none |
|---|---|---|---|---|---|---|---|
| 11-01 | 4177 | 3537 | 2745 / 1430 | 28 | 2 | 77 | 4 / 38 / 20 / 10 / 5 |
| 11-02 | 6529 | 5395 | 4038 / 2491 | 38 | 0 | 87 | 12 / 26 / 29 / 14 / 6 |
| 11-03 | 9654 | 7711 | 5957 / 3697 | 59 | 0 | 86 | 17 / 29 / 22 / 13 / 5 |
| 11-04 | 10160 | 8091 | 6418 / 3742 | 51 | 0 | 71 | 11 / 26 / 12 / 17 / 5 |
| 11-05 (partial) | 5113 | 4083 | 3282 / 1831 | 14 | 0 | 30 | 3 / 8 / 5 / 11 / 3 |

- Share accepted at step A: 63-66% every window.
- Cost per UTC day of the world journal: 11-02 $0.0718 (3609 calls), 11-03 $0.0710 (3706),
  11-04 $0.0755 (4037), 11-05 $0.0772 (4056). Under the $0.10 daily cap; about $2.3 per month,
  inside the approved $3. The estimate of `world-days-2026-11-01.md` (~$0.04 for a normal night)
  was low: weekday GDELT volume is about twice the first weekend's.

## Sample (from the reports)

| D | Area | Change | Harm | Outlet | Title |
|---|---|---|---|---|---|
| 11-02 | Speech | issue | 0.46 | wuwf.org | AI chatbots are becoming political advisers. Their answers can mislead voters |
| 11-02 | Education | issue | 0.11 | somersetlive.co.uk | 73 per cent of school pupils now pass off AI work as their own |
| 11-02 | Money | changed | 0.21 | thewestonmercury.co.uk | Ryanair to review pay freezes and AI use to counter jet fuel price surge |
| 11-03 | Education | limit | 0.13 | aol.com | Google will cut off search access for students at schools that reject AI tools |
| 11-03 | Law | issue | 0.93 | crookwellgazette.com.au | Young people at greatest risk from explicit 'deepfakes' |
| 11-04 | Work | changed | 0.90 | begadistrictnews.com.au | 'Existential' AI threat triggers Canva's mass job cuts |
| 11-05 | Security | issue | 0.70 | dailyliberal.com.au | Supercharged scams of concern in AI threat report |
| 11-01 | Work | added | 0.03 | intelligencer.ca | Wysera Launches an AI Agent That Writes Marketing Content in a Company's Own Voice |

## Findings

- Relevant to FR-014: schools, work, elections, health, scams; mostly small local outlets carrying
  AP/NPR copies, several languages.
- Repeats: adjacent windows share a GDELT day, so the same story is assessed for `D-1` and `D`
  (e.g. the Canva and "political advisers" stories) and could run in two consecutive bulletins.
  Fixed before the switch is turned on (`prompt-world-no-repeat-codex-2026-11-05.md`).
- Press releases pass as `added` (Wysera). Left for the FR-022 review once the stream is in the
  bulletin.
