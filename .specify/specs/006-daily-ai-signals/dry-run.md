# Dry-Run: Daily AI Signals Thresholds on Real Data

**Date**: 2026-10-17 | **Plan**: `plan.md` | **Spec**: `spec.md`
**Scripts and raw data**: `tmp/daily-signals-dryrun/` (gitignored, not committed):
`extract.py`, `extract_v2.py`, `analyze.py`, `digests/`, `calls/`, `calls-v2/`, `final.txt`.

## 1. Inputs and method

| Item | Value |
| --- | --- |
| Target days (LLM extraction) | 2026-10-12, 10-13, 10-14, 10-15, 10-16 (369 digest items) |
| Background days (no LLM) | 2026-08-03 .. 2026-10-11 public digests, titles + summaries only (1,703 items) |
| Article text | Local `data/ai_news.db` joined by URL: 369/369 target items matched, all with content >= 300 chars |
| Publisher | Registrable domain of the article URL (same rule as `storage/weekly.py::publisher_group`) |
| Provider | DeepSeek `deepseek-flash`, temperature 0, JSON mode, key from local `.env` |
| Calls | 39 of the 40 allowed (31 for v1 prompt on all 5 days, 8 for v2 prompt on 10-13) |
| Tokens / cost | 176,144 input + 97,611 output; about $0.17 at `reenrich_pilot.PRICES` |

Differences from the production design in `plan.md` (stated so nobody over-reads the numbers):

- Dry-run calls were **batched** (12 articles per call) with a **1,500-character** excerpt, to fit 5 days
  into 40 calls. Production uses **one call per article** with up to 6,000 characters; recall should be
  equal or better, precision is not expected to change much (same instructions and schema).
- First-seen history in the dry-run is the extracted target days plus a **lexical** check of background
  titles/summaries. Production instead extracts history-only days with the same prompt (plan, Decision 4).
- Rising and Cooling could not be computed: comparable (grounded) history starts on 2026-10-10, so no day
  has 14 comparable days yet. Only spikes were computed.
- The prompt used for 4 of the 5 days is v1 (article-level `novelty_claim` only). v2 adds an entity-level
  `is_new` flag; it was run on 2026-10-13 only (budget). The plan adopts v2.

## 2. Data facts that changed the plan

1. **Comparable data starts on 2026-10-10.** Public digests up to 2026-10-09 use the legacy 7 groups
   (`CATEGORY_ORDER`: "Business & Product", "Security", ...); from 2026-10-10 they use
   `REENRICH_TOPIC_ORDER` (grounded `daily-publish`). Legacy digests have different admission, often
   placeholder summaries ("Source: TechCrunch (main feed). Published at ..."), and one outlier day
   (2026-10-04: 302 items). Mixing them into windows would create fake trends.
2. **Reflection "Beam" first appears on 2026-10-05**, a legacy day: "Reflection debuts Beam, an
   open-weight AI model to rival Chinese models at lower compute cost". On 2026-10-16 (4 publishers) it is
   therefore not new; it surfaces as a **spike** (4 articles, 4 publishers, trailing mean 0) and as the
   top story of the day. SC-002 as written cannot be shown on a displayed day (see plan, Spec deltas).
3. Legacy digest URLs join to stored articles at 99-100% (checked 08-12, 09-16, 10-05, 10-07, 10-09),
   so history-only extraction by URL is feasible.
4. The model emitted `hardware` (Maia 300, NVIDIA B300, GB300 NVL72, M5 Ultra) and `regulation_policy`
   (EU AI Act, SR 11-7) as entity types although they were not offered: 24 entities lost. Both matter
   for investment-style reading. The plan adds `hardware` and `policy` types (Spec delta).
5. 102/459 extracted articles hit the 8-entity cap (listicles, newsletters); 42 had no primary entity.
   Daily volume of distinct stories is high: 50-80 stories per day, only 2-6 covered by >= 2 publishers.

## 3. Tuning log

| Run | Change | Effect |
| --- | --- | --- |
| 1 | Baseline: first-seen + primary role; lexical background, case-insensitive | New 20-45 per day; Beam and Elorian "Glimpse" suppressed by background |
| 2 | Single-token names: exact capitalization and vendor co-occurrence; distinctive names (multi-token, digits, CamelCase) case-insensitive | "Glimpse" no longer suppressed by "offers a glimpse into" (HackerRank); Beam still correctly suppressed (vendor "Reflection" co-occurs on 10-05) |
| 2 | Early signal (1 publisher) requires `novelty_claim` on an article where the entity is primary | New 10-23 per day |
| 2 | Vendor-prefix alias ("Reflection Beam" -> "Beam" with vendor Reflection AI); company sub-org suffixes (Research, Labs, Systems...) checked against background | "Reflection Beam" merged into "Beam"; "Google Research", "Cerebras Systems" no longer New |
| 2 | Same-day variant grouping by token prefix | "Muse Wonder Full" shown as variant of "Muse Wonder" |
| 3 | v2 prompt: entity-level `is_new` gates New (10-13 only) | Removed Facebook, Google Play, Character.AI, NVIDIA Run:ai, Gboard Rambler, Mind Robotics (hiring news) |
| 4 | Parentheticals stripped; packaging suffixes (74B, A9B, 24GB, FP8, Instruct, Preview, vN) collapse to one entity; `variant_of` tag against prior entities | "Nemotron 3.5 Bolt 74B-A9B 24GB" (10-15) resolved to the 10-13 entity; "Muse Spark Open" tagged variant of "Muse Spark"; "OpenCode 2.0" variant of "OpenCode" |
| 5 | Story edges: `model_release` and `product_launch` treated as one family ("launch") | Gemini 4 Argon 10-13 merged from 3 stories into one (5 publishers, 7 articles); Beam 10-16 into one (4/4); Muse Spark Open 10-15 into one (7/7) |
| 6 | Spike requires >= 2 distinct publishers on D and excludes entities already in New | Removed "Emergent" (5 articles, all from emergent.sh about its own product) and Muse Spark Open (already New) |

## 4. Final results (thresholds as in plan, Section "Thresholds")

Notation: C = confirmed (>= 2 publishers), E = early signal (1 publisher). Up to 8 New items shown (UI max).
My verdict per item: OK = concrete and genuinely new to the corpus; ? = concrete but uncertain novelty or
relevance; BAD = should not be listed.

### 2026-10-12 (56 items, 50 stories, 2 multi-publisher) - prompt v1

| New | Type / vendor | Count | Verdict |
| --- | --- | --- | --- |
| C Muse Wonder (+ variant Muse Wonder Full) | model / Meta | 6 pub | OK |
| E AlphaProof Nexus | model / Google DeepMind | 1 | OK |
| E Clef-omni | model / Cloudflare | 1 | OK |
| E Microsoft-Decision-1 | model / Microsoft | 1 | OK |
| E pplx-decider-v1.1-27b | model / - | 1 | OK (vendor Perplexity missed) |
| E Ambi | company | 1 | ? |
| E Atomic Machines | company | 1 | OK |
| E Multi-Agent Self-Supervision | technology / Sakana AI | 1 | ? (method name) |

Top stories: (1) Muse Wonder release - 6 publishers, 6 articles; (2) Claude false murder tip to
Philadelphia police - 2/2. Spikes: none (no comparable trailing days in the dry-run).
Events (by story): opinion_analysis 13, research 8, other 6, benchmark_result 5, model_release 4,
product_launch 4, security_incident 2, funding 2, regulation_policy 2, partnership 2, people_move 1,
infrastructure_deal 1.

### 2026-10-13 (90 items, 79 stories, 4 multi-publisher) - prompt v2

| New | Type / vendor | Count | Verdict |
| --- | --- | --- | --- |
| E Helix World | model / Noiz AI | 1 | OK |
| E LFM2.5-24B-A2B | model / - | 1 | OK (vendor Liquid missed) |
| E Nemotron 3.5 Bolt 74B-A9B 24GB | model / NVIDIA | 1 | OK (display name should drop packaging) |
| E Apple HomeView | product / Apple | 1 | ? |
| E Moltbook | product | 1 | ? |
| E PixelBoard | product | 1 | ? |
| E Your Algorithm | product / Meta | 1 | BAD (generic feature phrase) |
| E agent-engineer | product | 1 | ? (repository name) |

Top stories: (1) Gemini 4 Argon release - 5/7; (2) FBI arrests OpenAI employee over recording device -
3/3; (3) Muse Wonder follow-up - 2/2; (4) Mind Robotics hires Doug Field - 2/2.
Remaining split: "Gemini 4 Argon is now available in Devin" (partnership) stays separate - a distinct
event, acceptable.

### 2026-10-14 (73 items, 66 stories, 2 multi-publisher) - prompt v1

| New | Type / vendor | Count | Verdict |
| --- | --- | --- | --- |
| E Google Earth AI | product / Google | 2 art, 1 pub | BAD (existing product; v1 prompt) |
| E Grok Voice 3.0 | model | 1 | OK |
| E HiRO-ACEv2 | model | 1 | OK |
| E HiROv2 | model | 1 | ? (same paper as above; not merged) |
| E Orion-1 | model / Artemis Security | 1 | OK |
| E Amazon SageMaker JumpStart | product / Amazon | 1 | BAD (existing product; v1 prompt) |
| E Deep Review | product / Google | 1 | ? |
| E Epic Games Launcher | product / Epic | 1 | BAD (non-AI, existing; v1 prompt) |

Top stories: (1) OpenAI employee arrested (day 2) - 4/4; (2) Gemini 4 Argon on Google Cloud - 2/2.

### 2026-10-15 (92 items, 70 stories, 6 multi-publisher) - prompt v1

| New | Type / vendor | Count | Verdict |
| --- | --- | --- | --- |
| C Muse Spark Open (variant of Muse Spark) | model / Meta | 9 pub | OK |
| C Nemotron 3.5 Super VL | model / NVIDIA | 3 pub, 4 art | OK |
| C FLUX 3 Image Klein | model / Black Forest Labs | 3 pub | OK |
| C Black Forest Labs | company | 3 pub | BAD (established company, first seen in corpus only) |
| C Volvo | company | 2 pub | BAD (non-AI company) |
| E Granite Switch 4.1 | model | 1 | OK (vendor IBM missed) |
| E Attie | product / Bluesky | 1 | ? |
| E Bee Frontier (+ Bee) | product / Bee | 1 | ? |

Top stories: (1) Muse Spark Open - 7/7; (2) Nemotron 3.5 Super VL - 3/4; (3) FLUX 3 Image Klein - 3/3;
(4) Anthropic Q3 revenue ahead of IPO - 2/2; (5) Gemini 4 Argon robots + pricing page - 2/2 (weak:
one member is an SEO page from emergent.sh).
Spikes: NVIDIA (9 vs trailing mean 2.33, 5 pub), Apple (4 vs 1.0), Claude Code (4 vs 1.33), Hugging Face
(3 vs 1.0).

### 2026-10-16 (58 items, 51 stories, 3 multi-publisher) - prompt v1

| New | Type / vendor | Count | Verdict |
| --- | --- | --- | --- |
| C RTX Spark N1X | hardware-like product / Nvidia | 2 pub | OK |
| E GPT-Live-1.1 | model / OpenAI | 1 | OK |
| E GPT-Rosalind | model / OpenAI | 1 | OK |
| E Glimpse | model / Elorian | 1 | OK |
| E MAI-Base-2 | model / Microsoft | 1 | OK |
| E d1-ultra | model / Liquid | 1 | OK |
| E CodeOwnership | product | 1 | ? |
| E Evidence Desk | product | 1 | ? |

Suppressed as already seen: Beam (2026-10-05), Reflection AI (2026-10-05), Surface Laptop Ultra (10-07).
Top stories: (1) Reflection Beam - 4/4; (2) RTX Spark laptops + Surface Laptop Ultra reviews - 4/4
(over-merge: two products sharing the RTX Spark chip; borderline); (3) Muse Spark Open follow-up - 2/2.
Spikes: Beam (4 vs 0, 4 pub), Reflection AI (4 vs 0), Codex (3 vs 1.0), NVIDIA RTX Spark (3 vs 0.25),
Surface Laptop Ultra (3 vs 0).

## 5. Honest quality assessment

- **New (40 displayed items)**: 22 OK, 12 uncertain, 6 BAD. Five BAD items are on v1 days: 3
  established products on 10-14, Black Forest Labs and Volvo on 10-15. On the v2 day (10-13), the only
  BAD item is a generic feature phrase ("Your Algorithm"). v2 is a hypothesis
  supported by one day, not a measured improvement on all days. SC-001 therefore **fails with v1 and is
  not yet proven with v2**; the plan makes a v2 re-check on all 5 days a Phase B gate (task T5.3).
- **Generic terms**: none reached New. The stoplist rejected 10 mentions (Copilot, Transformer,
  transformers, Benchmark, X ...); it wrongly rejected "Z.ai" and "pi0" because of normalization bugs
  that the plan fixes (keep Unicode letters; do not strip "ai" when the rest is shorter than 3 chars).
- **Top stories (SC-003)**: after the launch-family rule, no day lists two entries for the same event.
  One borderline over-merge (RTX Spark / Surface, 10-16) and one weak 5th story (10-15).
  Days are thin: 2-6 multi-publisher stories, so the section often shows fewer than 5 rows - correct.
- **Spikes**: plausible. Big companies (NVIDIA, Apple) spike on busy release days; acceptable with counts
  shown. Spikes start once 3 comparable trailing days exist (from 2026-10-13 in production).
- **Event counts**: per story, `opinion_analysis` dominates (13-21 per day) and `other` is common.
  The UI shows "hard" events first and folds analysis/other (plan, UI).
- **Vendor recall** is weak for some models (Perplexity, Liquid, IBM missed): vendor only when named in
  the article text is the right grounding rule; the UI shows the vendor only when known.
- **Not measured**: Rising/Cooling (no 14 comparable days), production single-article prompt, v2 on 4 of
  5 days, PostgreSQL behaviour, page performance.

## 6. Final values carried into the plan

| Threshold | Value | Reason |
| --- | --- | --- |
| New confirmed | >= 2 distinct publishers | Spec default; matched every real release in the sample |
| New early | 1 publisher, entity `is_new` | Without the novelty gate, 20-45 early items per day |
| New eligibility | type not in {person, other}; primary in >= 1 article on D; `is_new` in >= 1 article on D; first_seen_day == D | Removed every BAD product item on the v2 day |
| Story edge | shared primary non-company entity + same event family; or shared primary company + same family + title Jaccard >= 0.2; or title simhash distance <= 6 | Launch family fixed all observed splits; Jaccard rule fired 4 times, simhash never (kept as safety net for articles without entities) |
| Top story minimum | >= 2 distinct publishers, max 5 | Single-article "top stories" carry no signal |
| Spike | count on D >= 3 articles, >= 2 publishers, >= 3x trailing mean (mean floor 1/3), >= 3 comparable trailing days (window up to 7) | Removed single-publisher self-promotion; caught Beam |
| Rising / Cooling | Spec values plus volume adjustment (plan) | Not validated; re-tune on 2026-10-30 (task T7.2) |
