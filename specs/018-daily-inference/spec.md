# Feature Specification: The Daily Inference

**Feature Branch**: `018-daily-inference`
**Created**: 2026-10-31
**Status**: Draft (brief; open owner questions at the end)
**Input**: Owner decisions of 2026-10-31, R4 report `docs/work/report-R4-2026-10-31.md`, sections
"Owner decisions" parts 1-3.

## The idea

The Daily Inference is a public outlet built on our real daily signals: the bulletin of the
**AI World Administration**, a report on the implementation of AI in human life, written for people.
The Administration is fiction; the world and every fact are real. The bulletin is openly loyal
("look how well it goes"): loyalty shows only in what is selected, in what order, and in fixed
phrases. It never shows in invented facts.

Sample (real data of 2026-10-30, lines picked by hand):

```
THE DAILY INFERENCE
Bulletin of the AI World Administration · Day 1430

REPORT ON THE IMPLEMENTATION OF AI IN HUMAN LIFE
The Administration reports steady progress.
In one day, 5 new models and 13 new products entered service.

Key results
• Speech: Edge0 released an open model that voices anyone in 23 languages.
• Daily life: Chrome now fills in forms for people, "Suggested by Gemini".
• Law: AI law firm Crosby bids for Weil Gotshal, a famed US law firm.

Autonomy milestone
• Open model GLM 5.3 built full Firefox exploit chains in under 48 hours,
  with zero human input (The Decoder).

Cooperation with humanity
• OpenAI set new behavioral guidelines for its models.
• Major AI firms back a way for sites to opt out of scraping.
  The Administration welcomes order.

Isolated incidents: 5.
Implementation continues. Full report (83) →
```

## Editorial rules (binding)

- **ER-1** Every line carries one real fact from the day's data with a link to its source; a
  vendor's claim stays attributed ("Block says ..."); a headline taken from an article names the
  outlet when the claim is the outlet's.
- **ER-2** Real companies act on their own: "Edge0 released", never "the Administration released".
  Nothing implies that a real company, person or government belongs to or endorses the
  Administration or us.
- **ER-3** No words in real people's mouths. The Administration may react ("welcomes"); real people
  are only quoted from sources.
- **ER-4** No real state symbols, flags, anthems or emblems; no Soviet or other historic state style.
  "Administration", never "government".
- **ER-5** Lines say what AI changed in the world (work, money, law, speech, science, daily life),
  not product specs. Model launches: at most two lines.
- **ER-6** Sharp news is not hidden; it is framed as success under a positive rubric ("Autonomy
  milestone", "Initiative from below"). Framing may choose words, never add facts ("incidents are
  being fixed" is forbidden unless a source says so).
- **ER-7** Human rules for AI (laws, courts, guidelines, opt-outs) go under "Cooperation with
  humanity" with a fixed welcoming phrase. Humans keep a dignified place.
- **ER-8** A cut headline is marked: "...instantly better*" with "* The rest of the headline is in
  the full report." Cuts only at a clause boundary.
- **ER-10** We retell other outlets' news in our own words, like a real news outlet: facts, our
  framing, the source named and linked. Short quotes only, in quotation marks; never their
  paragraphs or images. Archive texts are read to write and check the retelling, never published.
- **ER-9** Easter eggs kept for later: the owner is the Founder (honorary pension: a lifetime
  compute quota); a monthly "editorial chronicle" with real numbers about how agents run this
  project.

## User Scenarios & Testing

### User Story 1 - Daily bulletin from the day's data (Priority: P1)

After the daily signals of a day are ready, the system builds that day's bulletin: selected lines in
the sections above, the day's numbers, fixed phrases, a link to the full day.

**Why this priority**: everything else (page, Telegram) shows this text.

**Independent Test**: `ai-news bulletin build --date 2026-10-30 --dry-run` prints the bulletin for a
stored day; every line traces to an article of that day.

**Acceptance Scenarios**:

1. **Given** a ready day, **When** the bulletin is built, **Then** it has at most 4 key results, at
   most 2 model launches, at most 1 line per positive rubric, at most 2 cooperation lines, and every
   line has a source link.
2. **Given** a quiet day (`quiet = true`), **Then** the opening uses the quiet-day phrase ("A calm
   working Saturday") and empty sections are left out.
3. **Given** a day whose signals are `partial` or `unavailable`, **Then** no bulletin is published
   and the reason is logged.
4. **Given** a model-written line that fails the grounding check, **Then** the raw article title
   (with outlet) is used instead.

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

### User Story 3 - Telegram channel (Priority: P3)

Each new bulletin is posted once to a Telegram channel: the same text, names linked to sources,
"Full report" linked to the site.

**Why this priority**: the first place where people meet the outlet; free and automatic.

**Independent Test**: post a stored bulletin to a private test channel.

**Acceptance Scenarios**:

1. **Given** a new bulletin, **Then** exactly one post appears; a rerun does not post twice.
2. **Given** a Telegram failure, **Then** the bulletin and the site are unaffected and the failure is
   logged; the next run retries.

### User Story 4 - Weekly bulletin and monthly chronicle (Priority: P4)

A weekly bulletin from the stored week signals; a monthly editorial chronicle with real numbers
about the project (ER-9). Shape decided after P1-P3 run for two weeks.

### Edge Cases

- A day with no line in a section: the section is left out, never filled with "none".
- The same story from several outlets: one line, the outlet count shown only when 2 or more.
- An article without page text (about a third have only title and feed summary): Jev answers on
  what it has; low confidence lines are not selected.
- The day is rebuilt (signals recomputed): the bulletin is rebuilt; a posted Telegram message is not
  edited (decided 2026-10-31 (agent): posts are a record of the day as published).

## Requirements

### Functional Requirements

**Selection**
- **FR-001** A new Jev question `world_change` (choice: `added`, `changed`, `issue`, `limit`,
  `none`, with confidence), asked in a **separate request** per article of the day's digest, on the
  same `jev_state` text as the rubric. The validated admission rubric (`RUBRIC_VERSION`) is not
  touched. Answers are stored per article with a question version.
- **FR-002** Before it is used, the question is checked on at least 5 stored days against labels
  written by a separate session; the agreement and the threshold go into `records/`.
- **FR-003** Line selection per section: highest confidence, then outlet count; ER-5 caps; one line
  per story.

**Text**
- **FR-004** Fixed text (opening by day type, rubric names, welcoming phrases, closing) comes from a
  template library; no model call. Several variants per slot, chosen by date, so days differ.
- **FR-005** One model call per day writes, from the full text of each selected article: a story
  headline, a note of 3-6 sentences for the site, and a short line of 1-2 sentences for Telegram
  (owner 2026-10-31: the hand-made samples were too short). "Area: fact" form, a short context
  gloss for unknown names, one closing reaction of the Administration from the template library.
  Every sentence passes a grounding check like `parse_brief` (names and numbers present in the
  cited text); a failing sentence is dropped, a failing story falls back to the article title with
  outlet. Telegram text stays under the 4096-character message limit.
- **FR-006** The day number is days since 2022-11-30 (Day 1429 = 2026-10-29).

**Storage and API**
- **FR-007** A bulletin row per day: date, status, payload (sections, lines, links), versions,
  generated time. Built by the daily job after the signals; idempotent.
- **FR-008** Public `GET /api/news/bulletin?date=` returns the stored bulletin; existing APIs are
  unchanged.

**Site**
- **FR-009** `/` shows the bulletin (latest, or `?date=`); the digest page moves to `/daily` with
  the same query parameters; `/weekly`, `/monthly` and the APIs keep their URLs.
- **FR-010** The page footer and the channel description carry one line marking the frame as
  satire ("Satire. Every fact is real and linked.", owner decision Q2).

**Telegram**
- **FR-011** A poster sends each new bulletin once to the channel (bot token and channel id as
  secrets in prod `.env`); the message id is stored; a failure never blocks the daily job.

**World news about AI in human life** (owner yes 2026-10-31: "take it and build it", up to $3/month)
- **FR-014** Our 152 sources are AI and tech outlets; they report launches, not AI in courts,
  schools, churches, farms or city halls. A second stream reads general world news in any language
  (GDELT, free; plus a few general feeds) for stories of AI in human life.
- **FR-015** Free filters run first: the GDELT query itself (AI keywords and themes, last 24 h), then
  a local keyword and dedup filter on title and summary (several languages; ambiguous "AI" matches
  kept for Jev). Only the candidates go to Jev (`ai_relevant`, then `world_change`).
- **FR-016** This stream feeds only the bulletin; the digest at `/daily` keeps its sources (decided
  2026-10-31 (agent): an AI-made icon next to model releases would blur the digest).
- **FR-017** Lines from non-English sources are translated by the line writer (FR-005); the
  grounding check compares names and numbers with the original text.
- **FR-018** The first days are checked before the stream enters the bulletin: candidates per day,
  share accepted by Jev, cost per day, a sample of lines; numbers go into `records/`.

**Cost and safety**
- **FR-012** Paid calls of this feature are capped per day (Jev and the line writer) through the
  existing provider journal; expected total below $1 per month for items 1-6 and up to $3 per
  month with the world news stream (item 8).
- **FR-013** Nothing is posted anywhere else (Instagram, X) without a new owner decision.

### Key Entities

- **WorldChange**: per article: choice, confidence, question version, assessed time.
- **Bulletin**: per day: status (`ready`, `skipped`), sections with lines (text, area, link,
  outlet, article ids, origin `model` or `title`), numbers, versions, Telegram message id.

## Success Criteria

- **SC-001** On days with ready signals, the bulletin is on the site and in Telegram by 06:00 UTC.
- **SC-002** 100% of published lines link to a source of that day; 0 lines with a failed grounding
  check are published.
- **SC-003** Paid cost of the feature stays below $3 per month with the world news stream, below
  $1 without it (provider ledger).
- **SC-004** After the setup, the owner spends no time on daily posts.

## Implementation order (one item = one PR)

1. Jev `world_change` question, storage, offline check on stored days (FR-001, FR-002).
2. Bulletin builder with templates and title lines, CLI dry run (FR-003, FR-004, FR-006).
3. Model line writer with grounding (FR-005).
4. Bulletin storage, daily job step, API (FR-007, FR-008).
5. Home page as the newspaper, digest to `/daily` (FR-009, FR-010).
6. Telegram poster (FR-011).
7. Weekly bulletin; then the monthly chronicle (User Story 4).
8. World news about AI in human life: GDELT stream, free filters, Jev, bulletin only
   (FR-014..FR-018). Can start in parallel with item 2 once item 1 is done.

Each item: feature doc next to the main module first (AGENTS.md "Feature Docs Next To Code"),
then code and tests; reviewed by a different session.

## Owner decisions

- **Q1** (yes, 2026-10-31) The home page looks like an official bulletin (masthead, columns,
  serif type, issue number "Day N"), made modern and mobile-first; the design goes to a separate
  design session.
- **Q2** (yes, 2026-10-31) "Satire. Every fact is real and linked." only in the channel
  description and the page footer, not in every post. Why: screenshots travel without context;
  X requires parody accounts to say so; the second half is our selling point.

## Open questions for the owner

- **Q3** Telegram: the owner creates the channel and the bot once (about 10 minutes) and puts the
  token into prod `.env`. Recommendation: yes, after item 4.
