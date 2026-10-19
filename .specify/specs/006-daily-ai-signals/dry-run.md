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
  into 40 calls. Production uses **one call per article** with up to 6,000 characters and a different
  prompt (v3, with novelty quotes). Neither precision nor recall of v3 has been measured; that is T7.2.
- First-seen history in the dry-run is the extracted target days plus a **lexical** check of background
  titles/summaries. Production instead extracts history-only days with the same prompt and keeps them as mention
  evidence (plan, Decision 4).
- Rising and Cooling could not be computed: comparable (grounded) history starts on 2026-10-10, so no day
  has 14 comparable days yet. Only spikes were computed.
- The prompt used for 4 of the 5 days is v1 (article-level `novelty_claim` only). v2 adds an entity-level
  `is_new` flag; it was run on 2026-10-13 only (budget). The plan uses v3 (v2 plus quote and stricter
  retrospective rules), which was never run.
- All entity/story results below use the dry-run script's revision-1 identity keys, not the plan's
  reconciliation (revision 3). Clustering numbers are reproduced old-extraction evidence, not a
  validation of the combined production pipeline.

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
3. Legacy digest URLs join to stored articles at 98-100% by exact URL (08-12 39/39, 09-16 35/35, 10-05 45/45,
   10-07 60/61, 10-09 79/80; canonical fallback untested),
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

## 4. Final results (revision-1 rules)

Verdict column: `my verdict -> independent review verdict` where they differ (review of 2026-10-18,
evidence by corpus key). Section 7 summarizes the changes.

Notation: C = confirmed (>= 2 publishers), E = early signal (1 publisher). Up to 8 New items shown (UI max).
My verdict per item: OK = concrete and genuinely new to the corpus; ? = concrete but uncertain novelty or
relevance; BAD = should not be listed.

### 2026-10-12 (56 items, 50 stories, 2 multi-publisher) - prompt v1

| New | Type / vendor | Count | Verdict |
| --- | --- | --- | --- |
| C Muse Wonder (+ variant Muse Wonder Full) | model / Meta | 6 pub | OK |
| E AlphaProof Nexus | model / Google DeepMind | 1 | OK -> ? (article reports a study; model novelty unclear) |
| E Clef-omni | model / Cloudflare | 1 | OK |
| E Microsoft-Decision-1 | model / Microsoft | 1 | OK -> BAD ("Microsoft's Decision-1" already in the 2026-10-10 digest; alias/history miss) |
| E pplx-decider-v1.1-27b | model / - | 1 | OK (vendor Perplexity missed) |
| E Ambi | company | 1 | ? |
| E Atomic Machines | company | 1 | OK |
| E Multi-Agent Self-Supervision | technology / Sakana AI | 1 | ? -> OK (named method, explicitly introduced) |

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
| E Apple HomeView | product / Apple | 1 | ? -> OK (new smart display announced) |
| E Moltbook | product | 1 | ? -> BAD (article: "In late January, Moltbook launched"; v2 gate failed) |
| E PixelBoard | product | 1 | ? -> OK (newly released app) |
| E Your Algorithm | product / Meta | 1 | BAD -> ? (quoted named feature; launched on Instagram before) |
| E agent-engineer | product | 1 | ? -> OK (named open-source plugin) |

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
| E HiROv2 | model | 1 | ? -> OK (distinct component of HiRO-ACEv2, must not merge) |
| E Orion-1 | model / Artemis Security | 1 | OK |
| E Amazon SageMaker JumpStart | product / Amazon | 1 | BAD (existing product; v1 prompt) |
| E Deep Review | product / Google | 1 | ? -> OK (public release after pilots) |
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
| E Attie | product / Bluesky | 1 | ? -> BAD ("initially launched earlier this year") |
| E Bee Frontier (+ Bee) | product / Bee | 1 | ? (Frontier is new; grouping the existing Bee as its variant is wrong) |

Top stories: (1) Muse Spark Open - 7/7; (2) Nemotron 3.5 Super VL - 3/4; (3) FLUX 3 Image Klein - 3/3;
(4) Anthropic Q3 revenue ahead of IPO - 2/2; (5) Gemini 4 Argon robots + pricing page - 2/2 (weak:
one member is an SEO page from emergent.sh).
Spikes: NVIDIA (9 vs trailing mean 2.33, 5 pub), Apple (4 vs 1.0), Claude Code (4 vs 1.33), Hugging Face
(3 vs 1.0).

### 2026-10-16 (58 items, 51 stories, 3 multi-publisher) - prompt v1

| New | Type / vendor | Count | Verdict |
| --- | --- | --- | --- |
| C RTX Spark N1X | hardware-like product / Nvidia | 2 pub | OK -> ? (reviews; RTX Spark seen 09-03 and 10-07; N1X may be the same chip) |
| E GPT-Live-1.1 | model / OpenAI | 1 | OK |
| E GPT-Rosalind | model / OpenAI | 1 | OK -> ? (article launches an academic plan, not the model) |
| E Glimpse | model / Elorian | 1 | OK |
| E MAI-Base-2 | model / Microsoft | 1 | OK |
| E d1-ultra | model / Liquid | 1 | OK |
| E CodeOwnership | product | 1 | ? -> OK (named implemented tool) |
| E Evidence Desk | product | 1 | ? -> OK (named implemented tool) |

Suppressed as already seen: Beam (2026-10-05), Reflection AI (2026-10-05), Surface Laptop Ultra (10-07).
Top stories: (1) Reflection Beam - 4/4; (2) RTX Spark laptops + Surface Laptop Ultra reviews - 4/4
(over-merge: two products sharing the RTX Spark chip; borderline); (3) Muse Spark Open follow-up - 2/2.
Spikes: Beam (4 vs 0, 4 pub), Reflection AI (4 vs 0), Codex (3 vs 1.0), NVIDIA RTX Spark (3 vs 0.25),
Surface Laptop Ultra (3 vs 0).

## 5. Honest quality assessment

- **New (40 displayed items)**: my revision-1 count was 22 OK / 12 uncertain / 6 BAD; the independent
  review, with per-item evidence, counts **26 OK / 6 uncertain / 8 BAD**, and I accept its evidence.
  BAD items: Google Earth AI, SageMaker JumpStart, Epic Games Launcher (10-14, v1), Black Forest Labs and
  Volvo (10-15, v1), Attie (10-15, v1, launched earlier this year), Microsoft-Decision-1 (10-12, already
  in the 10-10 digest under "Microsoft's Decision-1"), and Moltbook on the **v2** day (retrospective:
  "In late January, Moltbook launched"). So v2 did not remove retrospective false positives; plan
  revision 2 adds prompt rules ("false when the article says it launched earlier") and a grounded launch
  quote. SC-001 **fails with v1 and is not proven with any prompt yet**; the plan makes a re-check with
  the final prompt on all 5 days a Phase B gate (task T7.2).
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
- **Not measured**: Rising/Cooling (no 14 comparable days), production single-article prompt (v3 with
  quotes was never run), v2 on 4 of 5 days, recall (missed eligible entities), PostgreSQL behaviour,
  page performance.
- **Lexical background is not deterministic evidence**: `analyze.py::lexical_hit` returns the first hit
  of the first alias in set order, so suppression dates can differ between runs (e.g. Meta 08-05 vs
  08-19). Displayed New did not change, but the dates in the "suppressed" lists are illustrative only.
  Beam's 10-05 title was checked directly.

## 6. Values carried into the plan (see plan Decision 5 for the evidence column)

| Threshold | Value | Reason |
| --- | --- | --- |
| New confirmed | >= 2 distinct publishers | Spec default; matched every real release in the sample |
| New early | 1 publisher, entity `is_new` | Without the novelty gate, 20-45 early items per day |
| New eligibility | type group not person/other; first_seen_day == D; primary and `is_new` with quote in the same article of D (plan revision 4) | v2 removed Facebook, Google Play, Character.AI, Run:ai on 10-13 but kept Moltbook (retrospective); grounded quote untested |
| Story edge | same event family and (shared primary-in-both non-org resolution key; or shared primary org key + title Jaccard >= 0.2; or simhash <= 6); greedy strict-majority linkage (plan revision 4) | Launch family fixed all observed splits; strict majority removed the RTX Spark/Surface over-merge (section 7); simhash never fired |
| Top story minimum | >= 2 distinct publishers, max 5 | Single-article "top stories" carry no signal |
| Spike | count on D >= 3 articles, >= 2 publishers, >= 3x trailing mean (mean floor 1/3), >= 3 complete comparable trailing days (window up to 7) | Computed on 2 days only (10-15, 10-16; 10-10/11 were not extracted); removed single-publisher self-promotion; caught Beam |
| Rising / Cooling | Spec values plus volume adjustment (plan) | Not validated; re-tune after 2026-10-30 (task T8.2) |

## 7. Post-review re-runs (2026-10-18, offline, no provider calls)

Changes after the independent review of revision 1 (plan "Review Response"):

- **Clustering**: average-link grouping (join a story only with edges to >= half its members; simhash
  edges only within the same event family) re-run on the same extractions:
  - 2026-10-16: RTX Spark laptop reviews (theverge, extremetech) and Surface Laptop Ultra reviews
    (arstechnica, wired) are now two 2-publisher stories instead of one 4-publisher story.
  - 2026-10-14: the x.com post about the OpenAI recording-device arrest no longer joins its story
    (4 -> 3 publishers) - a small recall loss.
  - Unchanged: Gemini 4 Argon 10-13 (7 articles / 5 publishers), Muse Spark Open 10-15 (7/7),
    Beam 10-16 (4/4), Muse Wonder 10-12 (6/6). The 10-15 Gemini robotics + pricing-page pair stays one
    story (known limit).
- **Identity**: revision-1 normalization merged distinct things (Glimpse the CT-inspection company on
  2026-10-06 vs Elorian's Glimpse model on 10-16; pplx-decider v1 vs v1.1; sizes 7B/70B; "1.2" vs "12").
  Revision 2 keeps versions/sizes/dots in keys and separates type groups. Not re-run end-to-end on this
  data (the analysis script still uses revision-1 keys); covered by T1.1/T2.3 tests and T7.2.
- **Fixtures**: `tmp/daily-signals-dryrun/fixtures/signals_2026-10-12..16.json` (titles, URLs,
  publisher domains, published_at, extracted entities and event types; no article bodies) for T0.1.
- **Cost**: revision-1 estimates for backfills were arithmetic errors; corrected in plan Decision 1
  ($0.00093 per article; 75 days ~$1.93-2.02).
- **Review 2 follow-up**: strict majority linkage (an article joins a story only with edges to more than
  half of its members; nulls in `published_at` ordered last, ties by key) gives exactly the same
  stories as the ">= half" rule on all five days (`cluster-avg-strict.txt` vs `cluster-avg.txt`).
  Fixtures regenerated with `article_id` (0 missing; 24 rows have null `published_at`).
- **Review 3 follow-up (revision 4)**: review 3 re-implemented the revision-3 identity rules on the
  fixtures and found that vendor spellings split Gemini 4 Argon ("Google" x15, "Google DeepMind" x2, none
  x3) and reduced the 10-13 story to 4/5 + 2/2. Revision 4 groups vendors into equivalence classes and
  builds story edges on resolution keys `(type_group, base_key)`, which matches how this dry-run's
  revision-1 keys behaved (7/5). Not re-run with a full revision-4 implementation; pinned in T1.2/T1.4.


## 8. Phase B validation (T7.1-T7.2, 2026-10-19)

**Branch code**: PR #39 head `8f30549` (no code change during the review window).
**Spend**: ledger estimate $0.6446 of the remaining $1.818 (hard stop not reached); the owner reports
**$0.14** actually billed by DeepSeek for this phase (finding 6). Budget accounting below uses the
ledger estimate, which only over-counts.
**Scripts** (not committed): `tmp/daily-signals-validate/` - `import_digests.py`, `seed_ledger.py`,
`backfill.sh`, `report.py`; dump `out-review.txt`; run reports `run-*.json`.

### Method

- Scratch DB: copy of local `data/ai_news.db`, `alembic upgrade head` (a42b750d0c44 -> b6d1f0a7c3e5).
  Public digests 2026-08-03..10-16 imported by read-only GET; 4 empty responses skipped
  (09-19, 09-20, 09-26, 09-27, kept `missing`). 2,072 digest items, 2,010 matched to local articles
  (97.0%, all by exact URL).
- Ledger seeded with the 778 saved Phase P responses (run id `seed-phase-p`, cost 0). They replay only for
  byte-identical v5 requests (same request key): all 369 target articles of 10-12..16 replayed, $0.
- History: production CLI, `--report-date 2026-10-16 --backfill-days 75 --max-calls 700
  --max-seconds 3500 --max-usd <remaining>`, repeated while `progress > 0`.
- Review: stored snapshots (displayed) plus the same recompute with `new_max`/`top_max`/`links_max`
  raised in a rolled-back transaction (uncapped). Same rubric and same reviewer as Phase P; items already
  judged in Phase P keep their verdict.

### Runs

| Run | Calls | States | USD | Progress | Terminal reason |
| --- | --- | --- | --- | --- | --- |
| targets (10-12..16) | 0 | - (369 replayed) | 0 | 369 | - (`ok`) |
| 1 | 700 | 699 response, 1 unknown | 0.238522 | 701 | `cap_reached` (calls) |
| 2 | 700 | 700 response | 0.322218 | 729 | `cap_reached` (calls) |
| 3 | 211 | 211 response | 0.083845 | 211 | - (`ok`) |
| 4 | 0 | - | 0 | 0 | - (`ok`, stop: progress 0) |

- 1,611 paid calls, $0.000400 per article on average (Phase P estimate $0.00088; history articles are
  short, see finding 1). The unknown attempt (transport error after 0.4 s, article 75661) is counted at
  its reservation ($0.002942); its article was extracted in the next run.
- Result: 2,010/2,010 articles `ok`, 0 failed or skipped, 3,081 active entities, 3 `needs_review`.
  09-12 and 10-04 stay incomplete only because of unmatched digest items (below 90% matched).

### New, 2026-10-12..16

| Day | Displayed OK / BAD / uncertain | Uncapped OK / BAD / uncertain | Changes against T1.6 (cached, lexical history) |
| --- | --- | --- | --- |
| 10-12 | 7 / 0 / 1 | 9 / 2 / 2 (13) | Displayed identical. Hidden: Gemini agent is now New (BAD-identity) |
| 10-13 | 4 / 1 / 3 | 8 / 1 / 5 (14) | LFM2.5-24B-A2B shown #3 (BAD-identity), pushes Apple HomeView below the cap |
| 10-14 | 6 / 1 / 1 | 10 / 1 / 2 (13) | "dynamic workflows" (Anthropic) shown #8 (BAD-generic) |
| 10-15 | 8 / 0 / 0 | 8 / 2 / 3 (13) | identical |
| 10-16 | 6 / 1 / 1 | 7 / 1 / 2 (10) | Surface Laptop Ultra shown #1 as confirmed (BAD-retrospective); SAT below the cap |
| **Total** | **31 / 3 / 6 = 77.5% OK, 7.5% BAD** | **42 / 7 / 14 of 63 = 67% OK, 11% BAD** | T1.6: 34 / 0 / 6 displayed; 42 / 3 / 14 uncapped |

New BAD items (the others are Phase P verdicts: Blueprints AI established, Maka non-AI, "on-demand
capacity mode" generic, all still hidden by the cap):

- **Surface Laptop Ultra** (10-16, displayed #1, 3 publishers): review articles; the laptop was
  covered on 10-07 ("The first Nvidia RTX Spark laptops cost up to $7,000"), but that history article has
  no content locally and its extraction is empty (finding 1). Quote: "Microsoft is throwing both arms
  around the new Nvidia RTX Spark platform with the Surface Laptop Ultra".
- **LFM2.5-24B-A2B** (10-13, displayed #3): a size variant of the LFM2.5 family seen on 08-06
  (LFM2.5-2.6B). Same `family_key` `lfm2.5`, but vendor "LiquidAI" and "Liquid AI" give different vendor
  classes, so `same_family` fails (finding 2).
- **dynamic workflows** (10-14, displayed #8): "a brand new feature, announced on Friday, called dynamic
  workflows"; a feature of an existing product with a generic name, announced five days earlier
  (same verdict as "on-demand capacity mode" in Phase P).
- **Gemini agent** (10-12, hidden #12): "Gemini Agents" was extracted on 10-08 and the same Google post
  was in the 10-09 digest title-only (empty extraction); the plural gives a different key (finding 3).

Recall (the 42 launch entities of Phase P, uncapped list): **34/42 = 81%**, unchanged. Missed as in
Phase P: PixelBoard, OpenCode 2.0, GenoMorph, Devin Oncall, OGX, Kilo Desktop, CodeOwnership, Evidence Desk.

### Named checks (T7.2 done-when)

| Check | Result |
| --- | --- |
| Displayed OK >= 75%, BAD <= 10% | met: 77.5% / 7.5% |
| No generic, non-AI or established-company item displayed | **missed**: "dynamic workflows" (generic) on 10-14 |
| Same, uncapped New | **missed**: + "on-demand capacity mode", Maka, Blueprints AI (hidden, as in T1.6) |
| Moltbook (10-13), Attie (10-15) not New | met |
| Beam not New on 10-16, spike and top story | met: spike 4 vs 0 (4 publishers), top story 4/4 |
| Muse Spark Open New on 10-15 | met (confirmed, 9 publishers) |
| Elorian Glimpse New on 10-16, separate from the 10-06 Glimpse company | met (`auto:artifact:glimpse` vs `auto:org:glimpse`) |
| No duplicate top story | met on all five days (Surface and RTX Spark stay separate on 10-16) |
| Membership precision >= 90% | strict **89%** (59/66), lenient 98% (65/66) - see below |
| Prompt or stoplist change | none (`daily-signals-extract-5`) |

Membership (all multi-publisher stories, uncapped, 18 stories / 66 member articles): wrong members are
the 6 emergent.sh SEO pages (pricing, "alternatives", comparisons) in the 10-15 "Gemini 4 Argon vs
Gemini 3.1 Pro" story (on the model, not an event; known since Phase P) and the "AI Weekly Issue #537"
roundup in the 10-13 Muse Wonder follow-up. Strict counts all 7 as wrong; lenient accepts the SEO pages
as same-entity coverage. Top stories are identical to Phase P and T1.6 on all five days.

Spikes: 10-15 identical to T1.6 (GPT-6 Astra, Nvidia, Black Forest Labs, Gemini 3.8 Flash, Google
DeepMind, Apple). 10-16: Beam, RTX Spark, Reflection, DeepSeek; Surface Laptop Ultra is no longer a spike
because it is now (wrongly) New. Rising and Cooling cannot be measured yet (first eligible day 10-23).

### Findings (written down, not fixed: no code change during the review window)

1. **History is mostly title-only in the local DB.** 1,199 of 1,641 history articles (73%; 08-03..10-09)
   have under 300 characters of content locally; the model returns no entities for 857 of them, and they
   still count as extracted, so those days are `complete`. Target days have full content. First-seen is
   therefore weaker here than in production would be if production stores content (not checked:
   production is off limits). Surface Laptop Ultra and part of Gemini agent come from this. Design
   question for the coordinator: should a title-only article count toward the 90% completeness, and
   should the operator guide warn about it?
2. **Glued vendor suffix splits vendor classes**: "LiquidAI" is not normalized to "liquid" (the company
   suffix rule only strips a separate "AI" token), so packaging suppression and `variant_of` fail across
   the two spellings. Candidate fix: vendor alias or suffix handling for a glued "AI"/"Labs", with a T1.1 test.
3. **Plural names are separate entities** ("Gemini Agents" vs "Gemini agent"). Candidate fix: an
   operator alias (no code), or singular folding of the last token for artifacts (risky for names like
   "Llama Stacks"; needs a test).
4. **Generic feature names still pass** (lowercase common-word names: "dynamic workflows",
   "on-demand capacity mode"). Candidate fix: treat an all-lowercase name made only of common words as
   not New; needs a test and a re-measure ($0, cached).
5. **Strict membership 89%** comes from one SEO cluster on 10-15, unchanged since Phase P.

6. **The ledger over-estimates cost about 4.6x.** `priced_usage` (shared with `reenrich_pilot`) prices
   every input token at $0.30/M and output at $1.20/M and ignores DeepSeek cache hits. This phase used
   1,462,238 input tokens (685,440 cache hits, 47%: the system prompt repeats) and 168,536 output
   tokens over 1,610 responses: $0.6409 by the formula, $0.14 billed. Safe direction (caps stop early),
   but run reports, the $0.0009-per-article figure in `docs/daily-signals.md` and the owner's
   backfill cap are read against inflated numbers. Official `deepseek-flash` prices
   (api-docs.deepseek.com/quick_start/pricing, per 1M tokens, peak = 01:00-04:00 and 06:00-10:00 UTC
   on weekdays, off-peak half): cache hit $0.006, cache miss $0.30, output $1.20 at peak. The ledger
   formula equals the peak miss/output prices but charges cache hits at the miss price and ignores
   off-peak. Re-priced per call from the ledger timestamps (1,282 off-peak, 328 peak calls): $0.2626.
   The billed $0.14 is lower still (not explained here; billing may lag or include a discount).
   Candidate fix: price cache-hit tokens separately (peak price, so it stays an upper bound), keep
   ignoring off-peak; say in the guide that the figure is an upper bound.

Fixes 2-4 are deterministic and can be re-measured on this scratch DB with `--recompute-only` ($0) after
the review window, together with the review findings (checkpoint 3 step 3).

## 9. Re-measure after the PR #39 review fixes (2026-10-19)

**Code**: `55ebe21` (F1-F22, N1-N3). **Spend**: ledger estimate $0.4265 of the approved $1.10 for the
F18 re-extraction (1,170 paid calls; at list prices well below that, see finding 6); validation total by
the ledger $1.7531 of $2.50. No other paid calls.

Method: the schema changed (F9), so the scratch DB was rebuilt from a fresh copy of `data/ai_news.db`
and the saved digests (offline, same 2,072 items, 2,010 matched). The same ledger replayed every
unchanged request ($0): 840 articles. The 1,170 articles with under 300 characters of content and a
usable RSS summary got a new request text ("Title + Summary", F18) and were extracted again
(`fix-01..03.json`: 700 + 470 calls, then progress 0). Input kinds recorded in the provenance: 811
`full` (content >= 300 characters, history and target days), 1,170 `title_summary`, 29 `title_only`.
Same rubric, same reviewer; items judged before keep their verdict. Dump: `tmp/daily-signals-validate/out-review-fixes.txt`.

### New, 2026-10-12..16 (before = section 8)

| Day | Displayed OK / BAD / uncertain | Uncapped OK / BAD / uncertain | Changes |
| --- | --- | --- | --- |
| 10-12 | 7 / 0 / 1 (was 7 / 0 / 1) | 9 / 1 / 2 of 12 (was 9 / 2 / 2) | Gemini agent gone (F21) |
| 10-13 | 5 / 0 / 3 (was 4 / 1 / 3) | 8 / 0 / 6 of 14 (was 8 / 1 / 5) | LFM2.5-24B-A2B gone (F20); Apple HomeView shown; Joule Assistants new, hidden (uncertain: "new and expanded") |
| 10-14 | 7 / 0 / 1 (was 6 / 1 / 1) | 10 / 0 / 2 of 12 (was 10 / 1 / 2) | "dynamic workflows" gone (F22); Deep Review shown |
| 10-15 | 7 / 0 / 1 (was 8 / 0 / 0) | 7 / 1 / 3 of 11 (was 8 / 2 / 3) | **Muse Spark Open suppressed (F19, false)**; "on-demand capacity mode" gone (F22); Trust in Depth shown |
| 10-16 | 7 / 0 / 1 (was 6 / 1 / 1) | 7 / 0 / 1 of 8 (was 7 / 1 / 2) | Surface Laptop Ultra gone (F18: the 10-07 history article now yields it); Code Review for Claude Code suppressed (F19) |
| **Total** | **33 / 0 / 7 = 82.5% OK, 0% BAD** (was 77.5% / 7.5%) | **41 / 2 / 14 of 57 = 72% OK, 3.5% BAD** (was 67% / 11%) | |

Recall (42 launch entities): **32/42** (was 34/42). The two new misses are both F19 suppressions:
Muse Spark Open (10-15) and Code Review for Claude Code (10-16, GA after a March research preview,
which OD1 counts as New; uncertain in the rubric).

### F19 side effects and variants (offline, $0)

F19 fired twice on these days, both times against the plan:

- Muse Spark Open, matched on 2026-09-03 in an RSS summary: "its roadmap includes the Muse Spark open
  weights release" (a plan, not a release). T7.2 requires Muse Spark Open to be New on 10-15.
- Code Review for Claude Code, matched on 2026-03-09 in a digest title (research preview rollout).

Surface Laptop Ultra, the case that motivated F19, is now removed by F18 alone (evidence from the
10-07 article's summary). Variants of the F19 text source on the same data
(`tmp/daily-signals-validate/f19_variants.py`):

| F19 texts | Suppressed on 10-12..16 |
| --- | --- |
| As implemented: in-scope article title + RSS summary, digest item title + summary, all days | Muse Spark Open, Code Review for Claude Code |
| Digest item title + summary only (the data the gate's rule used), all days | Code Review for Claude Code |
| Digest items only, from 2026-08-03 | none |
| As implemented, from 2026-08-03 | Muse Spark Open |

The code keeps F19 as specified; the choice of text source is a coordinator decision (see the reply).

### Named checks (T7.2 done-when)

| Check | Before (section 8) | After |
| --- | --- | --- |
| Displayed OK >= 75%, BAD <= 10% | 77.5% / 7.5% | **82.5% / 0%** |
| No generic, non-AI or established-company item displayed | missed ("dynamic workflows") | **met** |
| Same, uncapped | missed (4) | missed: Maka (non-AI), Blueprints AI (established), both hidden |
| Moltbook, Attie not New | met | met |
| Beam not New, spike and top story | met | met |
| Muse Spark Open New on 10-15 | met | **missed (F19)**; still the top story and now a spike |
| Elorian Glimpse New on 10-16, separate from the Glimpse company | met | met |
| No duplicate top story | met | met |
| Membership precision >= 90% | 89% strict / 98% lenient | unchanged (top stories identical); accepted by the coordinator |

Spikes: 10-15 Muse Spark Open (9 vs 0) joins and Apple drops below the cap; 10-16 Surface Laptop Ultra
is a spike again (3 vs 0) instead of a false New. Top stories identical on all five days.

## 10. Re-measure after the F19 decision (2026-10-19)

**Code**: `1b4c631` (F19 reads published digest items only; texts with a not-yet-released word are
ignored; snippet recorded). **Spend**: $0 (`--recompute-only`, 0 calls). Dumps:
`tmp/daily-signals-validate/out-review-f19-ai_news-prodwindow.txt` and `out-review-f19-ai_news.txt`.

The scratch DB also holds local digests from 2026-02-28..08-02 (a local artifact; production digests
start 2026-08-03). Numbers are given for a copy with the production digest window (main result) and for
the scratch DB as is.

| Day | Displayed OK / BAD / uncertain | Uncapped OK / BAD / uncertain | Change against section 9 |
| --- | --- | --- | --- |
| 10-12 | 7 / 0 / 1 | 9 / 1 / 2 of 12 | none |
| 10-13 | 5 / 0 / 3 | 8 / 0 / 6 of 14 | none |
| 10-14 | 7 / 0 / 1 | 10 / 0 / 2 of 12 | none |
| 10-15 | 8 / 0 / 0 | 8 / 1 / 3 of 12 | Muse Spark Open New again (confirmed, 9 publishers, shown #1); Trust in Depth below the cap |
| 10-16 | 7 / 0 / 1 | 7 / 0 / 2 of 9 | Code Review for Claude Code New again (hidden #9; uncertain) |
| **Total** | **34 / 0 / 6 = 85% OK, 0% BAD** | **42 / 2 / 15 of 59 = 71% OK, 3.4% BAD** | section 9: 82.5% / 0%, 72% / 3.5% |

- Recall: **34/42** (section 9: 32/42; section 8: 34/42). Misses as in Phase P: PixelBoard, OpenCode
  2.0, GenoMorph, Devin Oncall, OGX, Kilo Desktop, CodeOwnership, Evidence Desk.
- F19 suppressions: none on these days (`on-demand capacity mode` stays refused by F22). On the scratch
  DB as is, the local 2026-03-09 digest title "Anthropic rolls out Code Review for Claude Code ..." still
  suppresses Code Review for Claude Code (no not-yet-released word in that text); everything else is
  identical (uncapped 42 / 2 / 14 of 58, recall 33/42). Production has no digests before 2026-08-03.
- Top stories identical to sections 8-9. Spikes: 10-15 back to the T1.6 list (GPT-6 Astra, NVIDIA,
  Black Forest Labs, Gemini 3.8 Flash, Google DeepMind, Apple); 10-16 Beam, RTX Spark, Reflection,
  DeepSeek, Surface Laptop Ultra.

T7.2 checklist: displayed OK >= 75% / BAD <= 10% met (85% / 0%); no generic, non-AI or established item
displayed met; uncapped still holds Maka (non-AI) and Blueprints AI (established), both hidden;
Moltbook and Attie not New met; Beam not New, spike and top story met; **Muse Spark Open New on 10-15
met**; Elorian Glimpse New on 10-16 and separate met; no duplicate top story met; membership 89% strict /
98% lenient (accepted by the coordinator).
