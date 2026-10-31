# Feature Specification: The Daily Inference

**Feature Branch**: `018-daily-inference`
**Created**: 2026-10-31
**Status**: Ready for phase A (owner decisions Q1, Q2, Q4 recorded; Q3 deferred to phase B)
**Input**: Owner decisions of 2026-10-31, R4 report `docs/work/report-R4-2026-10-31.md`, sections
"Owner decisions" parts 1-3, and the owner's answers recorded below.

## The idea

The Daily Inference is a public outlet built on our real daily signals: the bulletin of the
**AI World Administration**, a report on the implementation of AI in human life, written for people.
The Administration is fiction; the world and every fact are real. The bulletin is openly loyal
("look how well it goes"): loyalty shows only in what is selected, in what order, and in fixed
phrases. It never shows in invented facts. We retell other outlets' news in our own words with the
source linked, like a real news outlet; only the framing is ours.

The voice, the structure of an issue, the fixed phrases and samples on real days are in
[`voice.md`](voice.md).

## Editorial rules (binding)

- **ER-1** Every story carries real facts from the day's data with a link to its source; a vendor's
  claim stays attributed ("Block says ..."); an outlet's own claim names the outlet.
- **ER-2** Real companies act on their own: "Edge0 released", never "the Administration released".
  Nothing implies that a real company, person or government belongs to or endorses the
  Administration or us.
- **ER-3** No words in real people's mouths. The Administration may react ("welcomes"); real people
  are only quoted from sources.
- **ER-4** No real state symbols, flags, anthems or emblems; no Soviet or other historic state style.
  "Administration", never "government".
- **ER-5** Stories say what AI changed in the world (work, money, law, speech, science, daily life),
  not product specs. Model launches: at most two stories.
- **ER-6** Sharp news is not hidden; when an AI system is the actor it is framed as success under a
  positive rubric ("Autonomy milestone"). Framing may choose words, never add facts ("incidents are
  being fixed" is forbidden unless a source says so).
- **ER-7** Human rules for AI (laws, courts, guidelines, opt-outs) go under "Cooperation with
  humanity" with a fixed welcoming phrase. Humans keep a dignified place.
- **ER-8** A cut headline is marked: "...instantly better*" with "* The rest of the headline is in
  the full report." Cuts only at a clause boundary.
- **ER-9** We retell in our own words. Short quotes only, in quotation marks; never the source's
  paragraphs or images. Archive texts are read to write and check the retelling, never published.
- **ER-10** Easter eggs kept for later: the owner is the Founder (honorary pension: a lifetime
  compute quota); a monthly "editorial chronicle" with real numbers about how agents run this
  project.
- **ER-11** Harm to real people (deaths, abuse, self-harm, a named private person in trouble) is
  never framed as success and never joked about: it is counted in "Isolated incidents" or left out.
- **ER-12** English only (R4 decision); sources in any language are retold in English.

## User Scenarios & Testing

### User Story 1 - Daily bulletin from the day's data (Priority: P1)

After the daily signals of a day are ready, the system builds that day's bulletin as described in
`voice.md`: headline, opening, sections, numbers, closing, link to the full day.

**Why this priority**: everything else (page, Telegram) shows this text.

**Independent Test**: `ai-news bulletin build --date 2026-10-30 --dry-run` prints the bulletin for a
stored day; every story traces to an article of that day.

**Acceptance Scenarios**:

1. **Given** a ready day, **When** the bulletin is built, **Then** it has at most 4 key results, at
   most 2 model launches, at most 1 positive-rubric story, at most 2 cooperation stories, and every
   story has a source link.
2. **Given** a quiet day (`quiet = true`), **Then** the opening is a quiet-day phrase and empty
   sections are left out.
3. **Given** a day whose signals are `partial` or `unavailable`, **Then** no bulletin is published
   and the reason is logged.
4. **Given** a model-written sentence that fails the grounding check, **Then** it is dropped; a story
   left without sentences falls back to the article title with outlet.
5. **Given** a story with harm to real people (ER-11), **Then** it is never the headline, never under
   a positive rubric and never gets a reaction.

### User Story 2 - Newspaper home page (Priority: P2)

`/` becomes the newspaper: the latest bulletin, with a date picker for earlier days. The current
digest with Daily Signals moves to `/daily` and stays as it is, linked from the bulletin as "Full
report".

**Why this priority**: the site is the outlet's home and the target of every "Full report" link.

**Independent Test**: open `/` and `/daily?date=2026-10-30` locally; old links `/?date=` still work.

**Acceptance Scenarios**:

1. **Given** a stored bulletin, **When** `/` is opened, **Then** the latest bulletin is shown.
2. **Given** an old link `/?date=2026-10-30`, **Then** the bulletin of that day is shown with a link
   to `/daily?date=2026-10-30`.
3. **Given** `/daily?date=...`, **Then** the page is the current digest page, unchanged.
4. **Given** a day without a bulletin, **Then** the page says so and links to `/daily` of that day.
5. **Given** publishing is switched off (FR-019), **Then** `/` shows the digest as today.

### User Story 3 - Channels, Telegram first (Priority: P3, after the site is checked)

Each new bulletin is posted once to a channel: the short version, outlet names linked to sources,
"Full report" linked to the site. Telegram is the first channel; others (Instagram, X, ...) follow
the same poster interface after their own owner decision.

**Why this priority**: where people meet the outlet; it starts only after the bulletin has run on the
site and passed the review (owner 2026-10-31: "first set up and check everything on the site, then
the channels").

**Independent Test**: post a stored bulletin to a private test channel.

**Acceptance Scenarios**:

1. **Given** a new bulletin, **Then** exactly one post appears; a rerun does not post twice.
2. **Given** a Telegram failure, **Then** the bulletin and the site are unaffected and the failure is
   logged; the next run retries.

### User Story 4 - Weekly bulletin and monthly chronicle (Priority: P4)

A weekly bulletin from the stored week signals; a monthly editorial chronicle with real numbers
about the project (ER-10). Shape decided after P1-P3 run for two weeks.

### Edge Cases

- A day with no story in a section: the section is left out, never filled with "none".
- The same story from several outlets or from both streams: one story, all outlets linked; the
  outlet count shown only when 2 or more.
- An article without page text (about a third have only title and feed summary): Jev answers on
  what it has; low-confidence stories are not selected.
- The day is rebuilt (signals recomputed): the bulletin is rebuilt; a posted Telegram message is not
  edited (decided 2026-10-31 (agent): posts are a record of the day as published).

## Requirements

### Functional Requirements

**Selection**
- **FR-001** The candidates of a day are the day's digest articles plus the world stream candidates
  (FR-015). Each gets one **separate** Jev request on the same `jev_state` text as the rubric, with
  four questions: `world_change` (`added`, `changed`, `issue`, `limit`, `none`), `area` (the list
  in `voice.md`), `actor` (`ai_system`, `people`, `organisation`) and `harm_to_people` (yes/no),
  each with confidence. The validated admission rubric (`RUBRIC_VERSION`) is not touched. Answers
  are stored per article with a question version.
- **FR-002** Before use, the questions are checked on at least 5 stored days against labels written
  by a separate session; agreement and thresholds go into `records/`.
- **FR-003** Mapping to sections, one story per event, ranked by confidence then outlet count:

  | Jev answer | Section |
  | --- | --- |
  | `added`, `changed` | Key results (max 4; model launches max 2) |
  | `issue`, actor `ai_system`, no harm to people | one positive rubric story (max 1) |
  | `issue`, other | counted in "Isolated incidents: N"; the top one may get one plain line |
  | `limit` | Cooperation with humanity (max 2) |
  | `none`, or below the confidence threshold | not shown |
  | `harm_to_people` yes | counted only (ER-11) |

- **FR-004** Headline of the day: the story with the highest confidence times outlet count among the
  shown stories, alarming ones included (ER-6), never a harm story. Fixed text (opening by day type,
  numbers line, rubric names, reactions, closing) comes from the phrase library in `voice.md`, no
  model call; variants chosen by date so neighbouring days differ.

**Text**
- **FR-005** One model call per day (DeepSeek flash by default, prices as in `signals_brief.py`)
  writes, from the full text of each selected article: the headline of the day, a story headline, a
  note of 3-6 sentences for the site and 1-2 sentences for Telegram, with a short gloss for unknown
  names; non-English sources are translated. Every sentence passes a grounding check like
  `parse_brief` (names and numbers present in the cited original text); failing sentences are
  dropped (User Story 1, scenario 4).
- **FR-006** The day number is days since 2022-11-30 (Day 1429 = 2026-10-29).

**Storage and API**
- **FR-007** A bulletin row per day: date, status (`ready`, `skipped`), payload (headline, sections,
  stories with texts, areas, links, outlets, article ids, origin `model` or `title`), numbers,
  versions, generated time, Telegram message id. Idempotent.
- **FR-008** Public `GET /api/news/bulletin?date=` returns the stored bulletin; existing APIs are
  unchanged.

**Schedule and switches**
- **FR-019** Two settings, both off by default: the bulletin as the home page, and posting to
  channels. Off means the bulletin is still built and stored, and visible at its own preview page
  `/bulletin?date=` (not linked from the site), while `/` stays the digest and nothing is posted
  (the kill switch). The site is checked on the preview page first (decided 2026-10-31 (agent):
  the debugging happens on real days without changing what visitors of `/` see).
- **FR-020** The bulletin runs as its own daily job at 04:00 UTC: after the digest and signals
  (02:00) and the archive capture (03:00); host lock and isolation as the archive job; a failure
  never changes other jobs. Telegram posting follows in the same job.

**Site**
- **FR-009** `/` shows the bulletin (latest, or `?date=`); the digest page moves to `/daily` with
  the same query parameters; `/weekly`, `/monthly` and the APIs keep their URLs.
- **FR-010** The page footer and the channel description carry "Satire. Every fact is real and
  linked." (owner decision Q2).

**Telegram**
- **FR-011** A poster sends each new bulletin once to the channel (bot token and channel id as
  secrets in prod `.env`); the message id is stored; a failure never blocks other jobs.
- **FR-021** Format: HTML parse mode, outlet names as links, link previews off, at most 4096
  characters; if longer, the lowest-ranked stories are dropped first.

**World news about AI in human life** (owner yes 2026-10-31: "take it and build it", up to $3/month)
- **FR-014** Our 152 sources are AI and tech outlets; they report launches, not AI in courts,
  schools, churches, farms or city halls. A second stream reads general world news in any language
  (GDELT, free; plus a few general feeds) for stories of AI in human life.
- **FR-015** Free filters run first: the GDELT query itself (AI keywords and themes, last 24 h), then
  a local keyword and dedup filter on title and summary (several languages; ambiguous "AI" matches
  kept for Jev). Only the candidates go to Jev (`ai_relevant`, then FR-001).
- **FR-016** This stream feeds only the bulletin; the digest at `/daily` keeps its sources (decided
  2026-10-31 (agent): an AI-made icon next to model releases would blur the digest).
- **FR-018** The first days are checked before the stream enters the bulletin: candidates per day,
  share accepted by Jev, cost per day, a sample of stories; numbers go into `records/`.

**Quality**
- **FR-022** The grounding check catches invented names and numbers, not distorted meaning (open
  question of R3). For the first 14 published days a separate session reviews each bulletin against
  its sources (`records/review-<date>.md`); a wrong story leads to a rule or prompt fix.

**Measurement**
- **FR-023** The site counts page views per day and route for `/` and `/daily` (the R4 plan: a
  `(day, route, count)` table, no IP, no cookies). The poster stores the channel's subscriber count
  daily (Bot API `getChatMemberCount`). Post views are not available through the Bot API; the owner
  sees them in the app.

**Cost and safety**
- **FR-012** Daily caps through the existing provider journal: Jev $0.05, the writer $0.10. Expected
  total below $1 per month without the world stream and up to $3 with it.
- **FR-013** Nothing is posted anywhere else (Instagram, X) without a new owner decision.

### Key Entities

- **WorldChange**: per article: the four answers of FR-001 with confidences, question version,
  assessed time.
- **Bulletin**: per day, as in FR-007.
- **PageViews**: per day and route: count.

## Success Criteria

- **SC-001** On days with ready signals, the bulletin is on the site by 06:00 UTC (and in the
  channels, once they are on).
- **SC-002** 100% of published stories link to a source of that day; 0 sentences with a failed
  grounding check are published; the review of FR-022 finds no story with distorted meaning in the
  last 7 of the 14 days.
- **SC-003** Paid cost stays below $3 per month with the world stream, below $1 without it
  (provider ledger).
- **SC-004** After the setup, the owner spends no time on daily posts.
- **SC-005** From day one, page views and subscribers are recorded daily (no target yet; the first
  month gives the baseline).

## Implementation order (one item = one PR)

Phase A, the site (no channels):

1. Jev questions, storage, offline check on stored days (FR-001, FR-002).
2. Bulletin builder with the phrase library (JSON, from `voice.md`) and title-only stories, CLI dry
   run (FR-003, FR-004, FR-006).
3. Model writer with grounding (FR-005).
4. Bulletin storage, daily job, switches, API, preview page (FR-007, FR-008, FR-019, FR-020).
5. World stream (FR-014..FR-018). Can start in parallel with item 2 once item 1 is done.
6. Home page as the newspaper, digest to `/daily`, page counter (FR-009, FR-010, FR-023); the
   design from a separate design session (Q1).
7. Review of 14 days on the preview page (FR-022); then the owner switches `/` to the bulletin.

Phase B, channels (after phase A):

8. Telegram poster and subscriber count (FR-011, FR-021, FR-023); needs Q3. Other channels after
   their own owner decision (FR-013).
9. Weekly bulletin; then the monthly chronicle (User Story 4). Each item: feature doc next to the main
module first (AGENTS.md "Feature Docs Next To Code"), then code and tests; reviewed by a different
session.

## Owner decisions

- **Q1** (yes, 2026-10-31) The home page looks like an official bulletin (masthead, columns,
  serif type, issue number "Day N"), made modern and mobile-first; the design goes to a separate
  design session.
- **Q2** (yes, 2026-10-31) "Satire. Every fact is real and linked." only in the channel
  description and the page footer, not in every post. Why: screenshots travel without context;
  X requires parody accounts to say so; the second half is our selling point.
- Retelling with sources like a real outlet, our own framing; longer notes than the first samples
  (2026-10-31).
- **Q4** (yes, 2026-10-31) The voice in `voice.md` is the starting library; it is tuned after the
  14-day review (item 7).
- World news about AI in human life, without a separate trial: "take it and build it", up to
  $3/month (2026-10-31).
- (yes, 2026-10-31) Footer credit "News discovery: GDELT Project" with a link (GDELT terms require
  citation).
- (yes, 2026-10-31) The digest Jev cap of FR-012 stays $0.05 per day; the world stream has its own
  Jev cap of $0.10 per day, inside the approved $3 per month.

## Open questions for the owner

- **Q3** (deferred by the owner 2026-10-31 to phase B) Telegram: the owner creates the channel and
  the bot once (about 10 minutes) and puts the token into prod `.env`.
