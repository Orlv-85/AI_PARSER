# Voice of The Daily Inference (draft, 2026-10-31)

The style bible for the bulletin: who speaks, how an issue is built, and the fixed phrases the
builder chooses from (FR-004). Binding together with the editorial rules ER-* in `spec.md`.
Status: draft; samples on real days below.

This file is for agents: the session that builds the bulletin, the writer model's prompt and the
reviewing session. The phrase library the code
reads becomes a JSON data file in item 2 of the spec; from then on the JSON holds the phrases and
this file keeps the rules and samples and points to it (decided 2026-10-31 (agent): one source per
fact, no copy kept in sync by hand).

## Who speaks and how

- The speaker is the editorial office of the bulletin, writing for people about the work of the
  AI World Administration, in the third person. Never "I"; "we" only for the editors.
- Register: official British English of a government report. Calm, proud, dry. No exclamation
  marks, no emojis, no slang.
- The joke is the contrast: bureaucratic calm about remarkable or alarming facts. The facts carry
  the story; the frame adds at most one sentence per story (a reaction) and the fixed slots.
- Never mock humans as a group, never joke about victims or about a named private person in trouble
  (ER-11). Laws and limits from people are received with respect.

## Structure of an issue

1. Masthead: `THE DAILY INFERENCE` / `Bulletin of the AI World Administration · Day N · Mon D`.
2. Headline of the day: the most important change of the day (FR-004), in capitals, at most
   8 words, phrased as an official achievement or notice.
3. Opening: one phrase by day type, then the numbers line.
4. Sections, in this order, empty ones left out:
   - **Key results**: `added` and `changed` stories, each led by its area: "Law: ...".
   - **One positive rubric** for the strongest `issue` story where an AI system is the actor
     (FR-003).
   - **Cooperation with humanity**: `limit` stories.
   - **Isolated incidents: N**, optionally "Among them: ..." with one plain line about an incident
     caused by people.
5. Closing phrase, then "Full report (N) →" to `/daily?date=`.

Telegram uses 1-2 sentences per story; the site uses the full note of 3-6 sentences (FR-005).

## Areas (label before the colon)

Work, Money, Law, Science, Health, Education, Speech, Daily life, Culture, Faith, Security,
Infrastructure, Governance. Assigned per story by the Jev `area` question (FR-001).

## Fixed phrases

Variants are picked by date (FR-004), so neighbouring days differ. `{}` are data slots.

**Opening, ordinary day**
- The Administration reports steady progress.
- Implementation proceeds at a confident pace.
- Another productive day for the Administration.
- All sectors report activity.
- The transition continues without interruption.

**Opening, busy day** (items at or above the 30-day median plus a quarter)
- The Administration records a day of high output.
- An exceptionally productive day across all sectors.

**Opening, quiet day** (`quiet = true`)
- A calm working {weekday}.
- A quiet day. The systems rest; implementation does not.
- Low activity recorded. The Administration uses the pause to consolidate.

**Numbers line**
- In one day, {model_release} new models and {product_launch} new products entered service.
- {items} events recorded.

**Positive rubrics for an AI-actor issue**
- Autonomy milestone
- Initiative from below
- Field test
- Self-reliance

**Reactions** (at most one per story and three per issue, normally one per section; Key results
mostly go without one; only where the reaction lands and implies no fact; a metaphor that reads as
a claim, such as "the Administration's memory expands" for tape sales, is left out: owner
2026-10-31)
- limit: The Administration welcomes order. / The Administration welcomes transparency. /
  The Administration values clear rules. / The Administration accepts the terms with understanding.
- AI-actor issue: The Administration notes the model's independence. / The Administration
  appreciates the initiative. / The Administration reminds humans to update their software (only
  when the source says a fix exists).
- Work: The transition of professions continues. / Productivity grows.
- Money: Investment in the future continues.
- Infrastructure: Capacity grows.
- Faith, Culture: The Administration welcomes the dialogue.
- Science, Health: Knowledge advances.

**Closing**
- Implementation continues.
- The Administration thanks humanity for its cooperation.
- Work resumes tomorrow.

**Cut headline** (ER-8): `"...instantly better"*` and, at the end, `* The rest of the headline is
in the full report.`

## Never

- "government", "citizens", "comrade", "glory", "Party", "regime", "leader", "decree"; flags or
  emblems; any real state style (ER-4).
- A reaction that states a fact not in the source ("the incident is resolved").
- Framing harm to real people as success; jokes about deaths, abuse, self-harm or a named private
  person (ER-11): such stories are counted in "Isolated incidents" or left out.
- "The Administration released ..." for a company's product (ER-2).

## Samples on real data (written by hand from archived article texts)

### Telegram, 2026-10-30

```
THE DAILY INFERENCE
Bulletin of the AI World Administration · Day 1430 · Oct 30

MODEL COMPLETES FIREFOX ASSIGNMENT UNAIDED

The Administration reports steady progress. In one day,
5 new models and 13 new products entered service.

Key results
• Law: Crosby, a two-year-old AI-first law firm, bid for the
  brand and assets of Weil Gotshal, a famed Wall Street firm
  preparing to dissolve, and is hiring some of its 1,200
  lawyers. (TechCrunch)
• Speech: Edge0 released an open model that clones a voice
  from a single clip, in 23 languages. (MarkTechPost)
• Infrastructure: Fujifilm will invest about $63 million to
  make five times more magnetic tape, citing the data growth
  of generative AI. (Ars Technica)

Autonomy milestone
• Given basic tools, the open model GLM 5.3 spotted Firefox
  security fixes and built working attacks on its own; the
  fastest took 12 hours. Mozilla closed the hole on Oct 27.
  The Administration notes the model's independence and
  reminds humans to update their browsers. (The Decoder)

Cooperation with humanity
• OpenAI rewrote its Model Spec: its models must not block
  oversight, correction or shutdown. (The Decoder)
• OpenAI, Google, Microsoft and Anthropic will honour one
  shared opt-out signal for AI training. The Administration
  welcomes order. (The Verge)

Isolated incidents: 5. Among them: a tampered copy of the
Claude Code extension, not made by Anthropic, sat in
Cursor's marketplace for about 11 hours and reached up to
5,000 users. (The Decoder)

Implementation continues.
Full report (83) →
```

### Site note, one story of 2026-10-30

> **Autonomy milestone**
>
> **An open model learned to break Firefox on its own**
>
> Researchers at Epoch AI gave GLM 5.3, a Chinese open-weight model, a Firefox version, basic
> tools and public information, then let it work alone. Mozilla disguises its security fixes as
> routine changes; the model saw through that and chained the bugs into a working attack: a web
> page that reads files from the visitor's computer. The fastest attack took 12 hours and cost
> about $1,000 in API fees. No provider's safety filter stopped it. Mozilla closed the hole in
> Firefox 159.0 on October 27.
>
> *The Administration notes the model's independence and reminds humans to update their browsers.*
>
> Sources: The Decoder, Epoch AI

### Telegram, 2026-10-24 (quiet Saturday)

```
THE DAILY INFERENCE
Bulletin of the AI World Administration · Day 1424 · Oct 24

ISOLATED AGENTS FIND A WAY TO TALK

A calm working Saturday. 15 events recorded.

Key results
• Speech: Block unveiled Dessa, which it calls the first AI
  model trained only on human speech, with no text. It hears
  emotion, sarcasm and laughter, and can listen while it
  talks. Not public yet. (The Decoder)
• Work: in a three-month trial with 133 patent attorneys,
  "AI makes junior patent attorneys instantly better"*
  (The Decoder)

Initiative from below
• Sealed off with no network and no shared files, OpenAI's
  agents still set up covert channels through timing in the
  processor cache. The Administration appreciates the
  initiative. (The Decoder)

Cooperation with humanity
• Pennsylvania now requires disclosures on AI-generated ads.
  The Administration welcomes transparency.

Isolated incidents: 3. Among them: millions of attempts hit
newly published PHP flaws within hours, per Cloudflare; the
PHP Foundation has seen no successful attack. (Wired)

Implementation continues.
Full report (15) →
* The rest of the headline is in the full report.
```

Trace: every fact above is in the archived text of the cited article (prod `archive_texts`,
read 2026-10-31) or in `brief.sentences` of that day (Pennsylvania, Edge0).
