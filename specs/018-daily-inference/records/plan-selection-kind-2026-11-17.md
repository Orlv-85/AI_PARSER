# Plan: spec 018 selection (F6), the kind of an article (2026-11-17)

Coordinator plan; owner go 2026-11-17 (label check, then the question).

## Problem
FR-022 review of 2026-11-09..14 (`records/review-summary-2026-11-09..14.md`, F6): vendor case
studies and blogs (Curative, NVIDIA recyclers, Apiiro/Qodo), newswire press releases (WhalesBot via
ACCESS Newswire, AI Rudder via Media OutReach), reports and forecasts (AI100, Gartner 1.7 million
jobs), explainers (Fact Check Team) pass as stories; 5 of 12 world stories were a concrete change.
`world_change` asks what AI changed, not what kind of text the article is.

## Proposal
1. A fifth Jev question `kind` in `world_change.py` (one request per article as now): `event` (a
   reported change: launch, decision, ruling, incident, measured finding), `forecast`, `opinion`,
   `explainer`, `promotion` (press release, vendor marketing or case study). `WORLD_CHANGE_VERSION`
   `world-change-2`.
2. Builder: only `event` articles are shown (Key results, cooperation, rubric, incident, reserve);
   the others are counted, not shown. No newswire host rule: decided 2026-11-17 (agent), the
   label check showed Jev catches the newswire copies (WhalesBot via finanznachrichten.de, AI
   Rudder via sina.com.hk), whose hosts a list would miss.
3. Before switching: label check of `kind` against the FR-022 reviewed stories of 2026-11-09..14
   (29 stories, F6 marks) and 2026-11-15..16; switch only if Jev agrees on most and never calls a
   real event `promotion`.

## Money (Jev, measured: about $0.00012 per article)
- Label check: about 40 articles, under $0.01.
- Every night after: about 110 articles with a slightly longer request, about $0.015 (now about
  $0.013).
- Past days are not re-assessed; a rebuild of a past day would cost about $0.015 for Jev plus the
  writer call.

## Risk
Fewer stories on some days (only events shown). Mitigated by the reserve and by the name-forms
gain of v0.1.183.
