# Prompt Gate (Phase P): Daily AI Signals extraction prompt on real data

**Date**: 2026-10-18 | **Plan**: `plan.md` (revision 5) | **Coordinator finding**: C1
**Scripts and raw data**: `tmp/daily-signals-gate/` (gitignored, not committed): `extract.py` (calls,
validation, cache), `analyze.py` (identity, New gate, clustering, spikes), `recall.py`, `calls.jsonl`
(per-call log), `calls/` (cached responses), `parsed/<version>/`, `out-v4.txt`, `out-v5.txt`.

## Result

**The pass bar is not met.** Both allowed prompt revisions were used. Best candidate:
`daily-signals-extract-5`.

| Bar | v4 | v5 (final candidate) |
| --- | --- | --- |
| New precision >= 80% OK (40 displayed items) | 27/40 = 67.5% - fail | 27/40 = 67.5% - fail |
| <= 10% BAD | 5/40 = 12.5% - fail | 4/40 = 10.0% - pass (at the limit) |
| No generic, non-AI or established-company items | fail (Epic Games Launcher, Maka, a book) | fail (Maka non-AI, Blueprints AI established 2025) |
| Moltbook (10-13) not New | fail (New, rank 11) | pass |
| Attie (10-15) not New | pass | pass |
| Muse Spark Open New on 10-15 | pass | pass |
| Elorian Glimpse New on 10-16 | fail (is_new without quote) | pass |
| Beam not New on 10-16 | pass (background 10-05; spike + top story) | pass (same) |
| Recall (T7.2 definition, uncapped New list) | 37/42 = 88% | 34/42 = 81% |
| Precision over all New items (uncapped) | not judged | 42/61 = 69% OK, 5/61 = 8% BAD |

Spend: **$0.682** of the $1.00 gate limit (778 calls, 0 non-200, 1,228,726 input and 261,243 output
tokens). Remaining validation budget: $2.50 - $0.682 = **$1.818**.

## Method

- Input: public digests 2026-10-12..16 (`tmp/daily-signals-dryrun/digests/`) joined by exact URL to local
  `data/ai_news.db`: 369 items, 369 matched, 0 unmatched.
- Request: plan Decision 1 body (`deepseek-flash`, temperature 0, thinking disabled, `max_tokens` 1200,
  JSON mode), `source = "Title: " + digest_title(article.title)[:512] + "\nContent: " + content[:6000]`,
  one call per article, schema recovery on validation failure. Responses cached by request key.
- Validation: plan Decision 1 rules 1-9 (model, finish reason, schema, event coercion, entity shape,
  grounding of name/canonical/vendor, syntactic quote check, type synonyms, primary and entity caps,
  stoplist, in-article duplicate merge).
- Identity: plan Decision 2 normalization, vendor classes with `VENDOR_ALIASES`, vendor-stripped base
  keys, family keys, reconciliation without overrides (no overrides exist yet).
- First-seen: extracted mentions on the five target days, plus a deterministic lexical background check
  of 2026-08-03..10-11 digest titles and summaries (days ascending, candidate names sorted). Multi-token
  or digit-bearing names match as a token subsequence; single common-word names need the exact
  capitalized word and the vendor's first token in the same item (dry-run rule).
- New gate: plan Decision 5 (group not person/other, not `?`, first_seen == D, primary + `is_new` with
  quote in one article of D, no earlier family entity, no background hit); confirmed >= 2 publishers;
  ordering confirmed, publishers, articles, type order, name; same-day family grouping; UI shows 8.
- Stories: plan Decision 3 strict-majority clustering; top stories >= 2 publishers, max 5. Spikes: plan
  thresholds with the extracted days as trailing days (10-15 and 10-16 have 3+ trailing days).
- Rubric (T7.2): OK / BAD-retrospective / BAD-established / BAD-generic / BAD-non-AI / BAD-identity /
  uncertain, judged from the article text (excerpts checked for every BAD and uncertain verdict).
  Named features of existing products, internal tools from customer case studies and startup profiles
  without a launch were judged "uncertain" (OD1 excludes features; the earlier dry-run review used "?"
  for the same class).
- Recall (T7.2): named entities of `model_release`/`product_launch` stories that I judged newly announced
  from the article (stories with >= 2 publishers and single-article stories), counted against the
  uncapped New list. Excluded as not new: Gemini 4 Argon (announced 2026-09-30), Beam (first seen
  2026-10-05), Microsoft-Decision-1 (10-10), RTX Spark (09-03), Friend 2 (July), existing products on
  new platforms (Grok 4.7 on Bedrock, Run:ai open-sourced), features (Figma Specs, Tool Recommendation,
  Pinecone on-demand mode), internal tools (Deckhand, Discovery AI, Tami, Scion).

## Prompt versions

| Version | Change | Effect |
| --- | --- | --- |
| `daily-signals-extract-3` (plan) | - | 20/20 base responses failed the schema check: the model put `event_type` and `novelty_claim` inside every entity object instead of at the top level. Schema recovery fixed all 20, but every article cost two calls ($0.00209 per article). Stopped after 20 articles ($0.042). |
| `daily-signals-extract-4` (revision 1) | Only the structure sentence: "Return one JSON object with exactly three top-level keys: entities, event_type and novelty_claim. entities: at most 8 objects, each with exactly these keys: ..." | 369/369 valid on the first call, 0 recoveries, $0.00085 per article. Quality problems: retrospectives (Moltbook "In late January, Moltbook launched"; Qwen 3.8-27B "On August 14"), features, internal tools and non-AI products as new; Glimpse `is_new` without a quote. |
| `daily-signals-extract-5` (revision 2) | `is_new`/`is_new_quote` clauses rewritten (full text below): restrict to AI models/products/companies, chips/devices and named techniques/benchmarks/datasets; exclude features, plans, bundles, internal tools, books, games, non-AI products; dated earlier releases and recounted past work are false; quote must contain the name as written | Moltbook and the book removed; Glimpse now New. Still New: Qwen 3.8-27B (retrospective quote despite the example), AlphaProtein Novo, Maka, Game Finder, Figma Specs, Deckhand. Over-correction: Devin Oncall ("Today we are launching Devin Oncall"), OGX (rename) and CodeOwnership lost `is_new`. $0.00088 per article. |

v5 replaces this v4 text:

```text
is_new: true only if the article presents this specific entity itself as newly released,
launched, announced, founded, renamed or emerging from stealth in this news; a new named
version counts as new; false for an existing thing that gets an update, a new feature, an
integration, a port, a partnership, a price change, a review or a mention, and false when the
article says it launched earlier,
is_new_quote: when is_new is true, a short exact substring of the article (at most 30 words)
that contains the entity name and states the release, launch or announcement; else null;
```

with:

```text
is_new: true only if the article presents this specific entity itself as newly released,
launched, announced, founded, renamed or emerging from stealth in this news, and the entity is
an AI model, an AI product or service, an AI company or lab, a chip or device, or a named
technique, benchmark or dataset; a new named version counts as new; false for an existing thing
that gets an update, a new feature, an integration, a port, a partnership, a price change, a
review or a mention; false for a feature, setting, label, plan, bundle or subscription inside
an existing product, for a tool a company built for its own internal use, and for books, games,
events and products unrelated to AI; false when the article dates the release before this news
(for example in late January, on August 14, earlier this year, last month) or recounts past
work,
is_new_quote: when is_new is true, a short exact substring of the article (at most 30 words)
that contains the entity name exactly as written in name and states the release, launch or
announcement (if no such substring exists, is_new is false); null when is_new is false;
```

Task line: `Task: daily-signals-extract-5.`; schema recovery suffix: `daily-signals-extract-5r`. Everything
else is the v4 text (plan Decision 1 with the structure sentence of revision 1).

## Per-day results (v5)

C = confirmed (>= 2 publishers), E = early signal (1 publisher). "Displayed" = the first 8 by the plan
ordering; the rest are New but hidden by the UI cap.

### 2026-10-12 (56 items, 50 stories, 2 multi-publisher)

| # | New | Type / vendor | Count | Quote states a launch? | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | C Muse Wonder | model / Meta | 6 pub | yes ("released a pair of new ... models on Monday") | OK |
| 2 | C Muse Wonder Full | model / Meta | 6 pub | yes (same quote) | OK |
| 3 | E Clef-omni | model / Cloudflare | 1 | yes ("Today, we're releasing Clef-omni") | OK |
| 4 | E pplx-decider-v1.1-27b | model / perplexity-ai | 1 | yes ("an update of our pplx-decider-v1-27b model"; new named version) | OK |
| 5 | E Blueprints AI | product | 1 | no ("will unveil a ... second-generation version"; incorporated 2025) | BAD-established |
| 6 | E Honeyjar | product | 1 | no ("Honeyjar is her answer to that question"; startup profile) | uncertain |
| 7 | E Maia 300 | hardware / Microsoft | 1 | partly ("Its successor, Maia 300, ships in 2027") | uncertain |
| 8 | E Atomic Machines | company | 1 | yes ("just emerged from six years of stealth") | OK |
| hidden | Multi-Agent Self-Supervision, Humanity's Sixth Sense, TasteVal, VisionQ | technology / benchmarks | 1 each | yes | OK x4 |

Suppressed correctly: Microsoft-Decision-1 (background 10-10), GPT-6 Luna (10-04), GPT-6 Sol (09-22),
Gemini agent (10-09). Top stories: Muse Wonder release (6 pub / 6 art); Claude false murder tip (2/2).

### 2026-10-13 (90 items, 77 stories, 4 multi-publisher)

| # | New | Type / vendor | Count | Quote states a launch? | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | C Game Finder | product / Google | 2 pub | partly ("using AI to build a recommendation engine called Game Finder"; Play Store feature) | uncertain |
| 2 | E Satlyt | company | 1 (2 art) | yes ("co-founded Satlyt, a new company") | OK |
| 3 | E AlphaProtein Novo | model / Google | 1 | no (year-review list: "We introduced AlphaProtein Novo") | BAD-retrospective |
| 4 | E Helix World | model / Noiz AI | 1 | yes ("Today we are introducing Helix World") | OK |
| 5 | E Nemotron 3.5 Bolt 74B-A9B 24GB | model / NVIDIA | 1 | yes ("releases on Thursday, Oct. 15") | OK |
| 6 | E Apple HomeView | product / Apple | 1 | yes ("the company's first smart display") | OK |
| 7 | E Deckhand | product / ShipStation Global | 1 | yes, but an internal tool in an AWS case study (v5 says false) | uncertain |
| 8 | E HomePod Mini 2 | product / Apple | 1 | yes ("Say hello to the HomePod Mini 2") | OK |
| hidden | agent-engineer, cuDF skills for Apache Spark, Priming | product / technology | 1 each | yes | OK x3 |
| hidden | Xbox Labs, Dynamic Model Escalation, 2026 Usage Policy | company / technology / policy | 1 each | group, capability inside Centor, policy "recently published" | uncertain x3 |

Moltbook: not New (v4 marked it New with the retrospective quote). Top stories: Gemini 4 Argon available
worldwide (6/8); Muse Wonder follow-up (3/3); FBI arrests OpenAI employee (3/3); Mind Robotics hires Doug
Field (2/2).

### 2026-10-14 (73 items, 67 stories, 2 multi-publisher)

| # | New | Type / vendor | Count | Quote states a launch? | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | E Deep Review | product / Google | 1 (2 art) | yes ("announce the public release of Deep Review") | OK |
| 2 | E Geospatial Reasoning agent | model / Google | 1 | no ("evolved ... from an early concept"; technical report) | uncertain |
| 3 | E Grok Voice 3.0 | model | 1 | yes ("Today, we're announcing Grok Voice 3.0") | OK |
| 4 | E HiRO-ACEv2 | model | 1 | yes ("We introduce HiRO-ACEv2") | OK |
| 5 | E HiROv2 | model | 1 | yes ("the new downscaling model, HiROv2") | OK |
| 6 | E Orion-1 | model / Artemis Security | 1 | yes ("has launched Orion-1") | OK |
| 7 | E Qwen 3.8-27B | model / Alibaba | 1 | no ("On August 14, ... Alibaba released Qwen 3.8-27B") | BAD-retrospective |
| 8 | E CedarDB Cloud | product / CedarDB | 1 | yes ("announced limited availability of CedarDB Cloud") | OK |
| hidden | Febris Monitoring System, Pi API, LendRecoup, PathSeer | product / technology | 1 each | yes | OK x4 |
| hidden | The X Subscription | product | 1 | subscription bundle (v5 says false) | uncertain |

Top stories: Gemini 4 Argon on Google Cloud (3/3); OpenAI employee arrested (2/2). Epic Games Launcher
(non-AI) is no longer New in v5.

### 2026-10-15 (92 items, 69 stories, 6 multi-publisher)

| # | New | Type / vendor | Count | Quote states a launch? | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | C Muse Spark Open (variant of Muse) | model / Meta | 9 pub | yes ("Meta launches Muse Spark Open") | OK |
| 2 | C Nemotron 3.5 Super VL | model / NVIDIA | 3 pub, 4 art | yes ("NVIDIA today released Nemotron 3.5 Super VL") | OK |
| 3 | C FLUX 3 Image Klein | model / Black Forest Labs | 3 pub | yes ("is today releasing open weights for FLUX 3 Image Klein") | OK |
| 4 | E Granite-Switch-4.1-8B | model / "Granite" | 1 | yes ("are released") | OK (vendor wrong: IBM not named) |
| 5 | E Figma Specs | product / Figma | 1 | yes, but "a new feature called Figma Specs" | uncertain |
| 6 | E Maka | product | 1 | yes ("a new streaming app for kids"); no AI product | BAD-non-AI |
| 7 | E Universal Cart | product / Google | 1 | yes (US availability after an I/O preview; shopping tool) | uncertain |
| 8 | E Bee Eclipse | hardware / Bee | 1 | yes ("along with Bee Eclipse, a ... device") | OK |
| hidden | Bee Frontier, DolphinBench, TheoPhysEval | hardware / benchmarks | 1 each | yes | OK x3 |
| hidden | Trust in Depth | technology / AWS | 1 | naming of an approach ("AWS calls it Trust in Depth") | uncertain |
| hidden | on-demand capacity mode | technology / Pinecone | 1 | feature | BAD-generic |

Black Forest Labs and Volvo are not New (BFL is a spike, 4 vs 0). Attie: not New. Top stories: Muse
Spark Open (9/9); Nemotron 3.5 Super VL (3/4); FLUX 3 Image Klein (3/3); Gemini 4 Argon vs Gemini 3.1
Pro (2 pub / 7 art - comparison and SEO pages, weak membership); Anthropic quarterly revenue (2/2).
Spikes: GPT-6 Astra (6 vs 1.33), Nvidia (6 vs 1.0), Black Forest Labs (4 vs 0), Google DeepMind (4 vs
1.33), Apple (3 vs 0.67), ComfyUI (3 vs 0).

### 2026-10-16 (58 items, 52 stories, 4 multi-publisher)

| # | New | Type / vendor | Count | Quote states a launch? | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | C Nvidia RTX Spark N1X (variant of NVIDIA RTX Spark) | hardware / Nvidia | 2 pub | partly ("processor is finally here"; reviews; RTX Spark seen 09-03) | uncertain |
| 2 | E GPT-Live-1.1 | model / OpenAI | 1 | yes (new named version) | OK |
| 3 | E Glimpse | model / Elorian | 1 | yes ("released its first model on Friday ... The model, Glimpse, is launching as a research preview") | OK |
| 4 | E MAI-Base-2 | model / Microsoft | 1 | yes ("completed pre-training our new ... model, MAI-Base-2") | OK |
| 5 | E d1-ultra | model / Liquid AI | 1 | yes ("Today, we release d1-ultra") | OK |
| 6 | E Code Review for Claude Code | product / Anthropic | 1 | yes (GA after research preview; a Claude Code feature) | uncertain |
| 7 | E Handwired | technology | 1 | yes ("Introducing Handwired") | OK |
| 8 | E Self-Organizing Agent Teams (SAT) | technology | 1 | yes ("Dubbed Self-Organizing Agent Teams (SAT), the framework") | OK |
| hidden | Nemotron-pretraining-Indic-v1 | dataset / NVIDIA | 1 | yes | OK |

Beam: not New (background 2026-10-05), spike 4 vs 0 with 4 publishers and the top story. Surface Laptop
Ultra: not New (background 10-07). Top stories: Reflection Beam (4/4); Muse Spark Open follow-up (2/2);
Surface Laptop Ultra review (2/2); NVIDIA RTX Spark and Kilo by Anaconda (2/2) - RTX Spark and Surface
stay separate stories. Spikes: Beam, NVIDIA RTX Spark, Reflection (4 vs 0-0.25), DeepSeek (3 vs 0),
Surface Laptop Ultra (3 vs 0).

### Tally

| Day | v5 displayed OK / BAD / uncertain | v4 displayed OK / BAD / uncertain |
| --- | --- | --- |
| 10-12 | 5 / 1 / 2 | 6 / 0 / 2 |
| 10-13 | 5 / 1 / 2 | 4 / 1 / 3 |
| 10-14 | 6 / 1 / 1 | 6 / 2 / 0 |
| 10-15 | 5 / 1 / 2 | 6 / 1 / 1 |
| 10-16 | 6 / 0 / 2 | 5 / 1 / 2 |
| Total | **27 / 4 / 9** | **27 / 5 / 8** |

v4 BAD: AlphaProtein Novo, Qwen 3.8-27B, Epic Games Launcher, Maka, "Artificial Intimacy" (a book).

### Recall (v5, uncapped New list)

| Day | Newly announced launch entities | In New | Missed |
| --- | --- | --- | --- |
| 10-12 | Muse Wonder, Muse Wonder Full, Clef-omni, pplx-decider-v1.1-27b, Atomic Machines | 5/5 | - |
| 10-13 | Helix World, Nemotron 3.5 Bolt, Apple HomeView, HomePod Mini 2, PixelBoard, agent-engineer, Dynamic Model Escalation, Satlyt | 7/8 | PixelBoard (both versions: quote given, `is_new` false) |
| 10-14 | Grok Voice 3.0, HiRO-ACEv2, HiROv2, Orion-1, Deep Review, CedarDB Cloud, Pi API, OpenCode 2.0, GenoMorph, Febris | 8/10 | OpenCode 2.0 (new major version), GenoMorph (quote without the name) - both versions |
| 10-15 | Muse Spark Open, Nemotron 3.5 Super VL, FLUX 3 Image Klein, Granite Switch 4.1, Bee Eclipse, Bee Frontier, Devin Oncall, OGX (rename of Llama Stack), Universal Cart (GA after preview, OD1) | 7/9 | Devin Oncall, OGX (v5 over-correction; v4 had both) |
| 10-16 | Glimpse, GPT-Live-1.1, MAI-Base-2, d1-ultra, Handwired, Nemotron-pretraining-Indic-v1, Kilo Desktop, CodeOwnership, Evidence Desk, Code Review for Claude Code | 7/10 | Kilo Desktop (both), CodeOwnership and Evidence Desk (v5; v4 had them) |
| Total | 42 | **34 (81%)** | v4: 37 (88%; misses PixelBoard, OpenCode 2.0, GenoMorph, Glimpse, Kilo Desktop) |

Top-story check (SC-003): no day lists two entries for the same event. Weak membership: 10-15 "Gemini 4
Argon vs Gemini 3.1 Pro" (7 articles, 2 publishers, mostly SEO comparison pages).

## Findings beyond the prompt (for the coordinator; not changed in the plan)

1. **v3 as written cannot ship**: its structure sentence makes the model nest top-level fields in every
   entity (100% schema failures). Revision 1's sentence is required whatever else is decided.
2. **Remaining errors are mostly grey-zone judgments, not prompt-following failures**: 9 of 13 non-OK
   displayed items are features of existing products, internal or case-study tools, startup profiles and
   a chip review. A prompt can trade these against recall (v5 lost Devin Oncall, OGX, CodeOwnership while
   removing Moltbook and the book) but did not move displayed precision.
3. **Dated retrospectives survive the prompt** ("On August 14, ... released" passed v5 despite the
   example). A deterministic check would catch them: reject `is_new` when the quote names a month/date
   before the article's publication month or contains "earlier this year", "last year", "in late <month>"
   (validation rule, no provider cost).
4. **Quote check misses vendor-stripped names**: "Reflection AI introduced Beam" fails for name
   "Reflection Beam"; "Pluto, fresh out of stealth" for "Pluto Security"; GenoMorph's launch sentence
   precedes the name. Accepting the entity's base name (Decision 2) in the quote would recover some.
5. **Identity: product names given as vendors become vendor classes.** Some mention had vendor "Gemini",
   so "Gemini 4 Argon" got base key `4argon` (it is correctly not New, but the key is wrong). Decision 2
   rule 7 should strip only vendor classes that also occur as `org` entities, or never leave a remainder
   that starts with a digit (T1.1 test needed).
6. **Display order decides precision**: with 9-14 early items per day, the 8 shown are picked by type
   order then alphabet. Hidden items were better (15 OK / 1 BAD / 5 uncertain) than displayed ones
   because benchmarks and techniques rank below products.
7. Cost per article measured: $0.00085-0.00088 (plan estimate $0.00093); input ~1,600 tokens, output ~330.

## Options for the owner (checkpoint 1)

- **A. Accept v5 with the shortfall** (67.5% OK, 10% BAD, 81% recall), proceed to B2, and fix findings
  3-6 in code (deterministic retrospective check, base-name quote match, vendor-class rule, ordering
  that ranks models/benchmarks/techniques before products). Re-measure in Phase 7 with no extra prompt
  calls for the five days (cached).
- **B. Raise the gate limit** for a third revision (~$0.33 per full five-day run) that restores the v4
  launch wording for products while keeping the v5 retrospective and non-AI rules.
- **C. Change what New shows**: e.g. confirmed items plus early items whose type is model, hardware,
  benchmark, dataset or technology, with products only when confirmed - a product decision (OD1).

Recommendation: A, with the fixes from findings 3-6 as tasks in Phase 1, because the remaining errors are
judgment-grey and a third prompt round is unlikely to reach 80% without losing recall again.
