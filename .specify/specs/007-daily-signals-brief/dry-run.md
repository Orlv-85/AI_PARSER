# Dry-Run: Daily Signals Brief, One-Liners and Noise Rules (2026-10-12..18)

**Date**: 2026-10-19 | **Code**: none (throwaway script `tmp/007-brief-dryrun/dryrun.py`, not
committed) | **Spend**: 37 calls, ledger $0.0798 `deepseek-v4-pro` (cap $0.50) + $0.0207
`deepseek-flash` (cap $0.10), incl. the discarded first prompt run.

## 1. Inputs and method

- Production data, read-only: `GET /api/news/daily-signals?date=` and `GET /api/news/digests?date=` for
  2026-10-12..18 (saved as `sig-DD.json` / `dig-DD.json`). No database copy was needed: the packet uses
  the snapshot (as served) and the digest items (title, summary, url).
- Approximations against the planned code: the API carries at most 3 links per item, so folding,
  diffuse detection and spike reasons use those links and top stories only (the code uses all articles
  and all D stories); `new_suppressed` is not in the API (not needed).
- Calls: the exact body of plan "Brief" (temperature 0, thinking disabled, JSON mode, 900 max tokens),
  one recovery on validation failure, answers cached by request hash, caps checked before each call with
  a byte-bound reservation. The script's packet cap was 16,000 bytes and was never reached (max 9,886);
  the plan sets 12,000. Ledger prices: input $1.32 / output $3.96 per 1M (pro), $0.30 / $1.20 (flash).
- Prompt history: run 0 (quote limit "at most 25 words", no minimum) left 3 of 14 day/model pairs
  without a brief (pro 10-12 and flash 10-16: whole-sentence quotes over 25 words; flash 10-15:
  paraphrased quote twice). Run 1 used the plan's prompt (quotes 5-40 words; a 4-word title quote such
  as "Introducing Grok Voice 3.0" no longer counts as support) and exposed validator false positives
  (names from the `what` line such as "Hugging Face", publisher names such as "TechCrunch", "#1"). The
  validator was fixed as in plan rules 3, 5 and 7 and run 1's answers were re-validated from the cache
  ($0). Only that final state is reported below.

## 2. Briefs side by side (verbatim; ids are packet article ids)

Grounding check: each sentence read against the full title and summary of every cited article.
S = every fact and name is stated in the cited text; notes say where a sentence is weak.

### 2026-10-12 (56 items; packet 5362 bytes)

**deepseek-v4-pro** - ledger $0.0046, list $0.0042; attempts: 1770/561 tok ok

```text
1. Meta launched two new AI models, Muse Wonder and Muse Wonder Full, claiming they rival leading models from OpenAI and Anthropic based on internal testing. [a1,a2,a3]
2. Meta says its Muse Wonder Full model has frontier capabilities and that the Muse Wonder models mark a major leap toward personal superintelligence. [a2]
3. Cloudflare released Clef-omni, which accepts audio, video, image, and text input, and claims it is built on a Qwen3-Omni-30B-A3B-Instruct mixture-of-experts foundation. [a4]
4. Gartner's first Emerging Market Quadrant for AI Application Security named Enkrypt AI by Anaconda a Specialist, which Enkrypt reads as a sign the market is maturing. [a6]
5. Sakana AI's MASS method lets one language model improve itself by solving, judging, and refining workflows without a stronger teacher, though shared blind spots can let errors pass as progress. [a9]
```
Grounding: 1: S; 2: S; 'major leap' is Meta's claim, attributed; 3: S; 4: S; 5: S.

**deepseek-flash** - ledger $0.0010, list $0.0009; attempts: 1773/353 tok ok

```text
1. Meta launched two AI models, Muse Wonder and Muse Wonder Full, which Meta says match leading models from OpenAI and Anthropic on benchmarks, covered by 6 outlets. [a1,a2,a3]
2. Meta says the largest Muse Wonder version outperforms Anthropic's Claude Fable 5.1 and ranks just below Claude Opus 5.5 on the Artificial Analysis Intelligence Index. [a2]
3. Cloudflare released Clef-omni, which accepts audio, video, image, and text input, and says it is built on a Qwen3-Omni-30B-A3B-Instruct mixture-of-experts foundation. [a4]
4. Sakana AI's MASS method lets one language model improve itself by solving, judging, and refining workflows without a stronger teacher, though shared blind spots can let errors pass as progress. [a9]
```
Grounding: 1: S; 2: S; 3: S; 4: S.

### 2026-10-13 (90 items; packet 9450 bytes)

**deepseek-v4-pro** - ledger $0.0053, list $0.0050; attempts: 2732/439 tok ok

```text
1. Google began a wide rollout of Gemini 4 Argon to paying users, with lower-tier plans lacking full access, covered by 6 outlets. [a1,a2,a3]
2. Meta introduced the Muse Wonder series, comprising Muse Wonder and Muse Wonder Full, as its most capable models for personal and professional agentic tasks. [a5,a6]
3. An OpenAI engineer was arrested after the company said it discovered a sophisticated recording device hidden in one of its offices. [a7,a8,a9]
4. Rivian partner Mind Robotics hired Doug Field as president to lead its robotics effort, according to the startup. [a10,a11]
5. Google announced that users can now run private, vibe-coded apps on Android via Google Play without publishing them publicly. [a12,a13]
```
Grounding: 1: S; 2: S; 3: S; 4: S; 5: S.

**deepseek-flash** - ledger $0.0014, list $0.0013; attempts: 2735/442 tok ok

```text
1. Google says Gemini 4 Argon is now globally available, claiming it outperforms other frontier models on benchmarks and ranks first on the Vals Index, covered by 6 outlets. [a2,a1,a3]
2. Google says the model launches at an introductory price of $2 per million input tokens and $10 per million output tokens, with cached input tokens at 95% off. [a2,a3]
3. Meta introduced the Muse Wonder series, with Muse Wonder available through the Meta Model API and Muse Code and Muse Wonder Full available for Muse Code subscribers, covered by 3 outlets. [a5,a6]
4. An OpenAI engineer was arrested after the company said it found a recording device hidden in one of its offices, covered by 3 outlets. [a7,a8,a9]
5. Rivian hired former Ford EV chief Doug Field as president of its industrial AI and robotics venture Mind Robotics, which has over $1 billion in backing, according to TechCrunch. [a11,a10]
```
Grounding: 1: S; 2: S; 3: S; 4: S; 5: S.

### 2026-10-14 (73 items; packet 6453 bytes)

**deepseek-v4-pro** - ledger $0.0101, list $0.0095; attempts: 2051/695 tok sentence_count, 2062/494 tok ok

```text
1. Google Cloud announced that its new frontier model, Gemini 4 Argon, is available on Google Cloud for complex, multi-step business work, covered by 3 outlets. [a1,a2,a3]
2. OpenAI says it found a hidden recording device in one of its offices and used its models to identify the employee who planted it days earlier, covered by 2 outlets. [a4,a5]
3. x.ai announced Grok Voice 3.0, claiming it ranks first on Artificial Analysis's Speech-to-Speech Index with a score of 86.9. [a6]
4. Ai2 introduced HiRO-ACEv2, which can generate global 3 km climate data at about 1/300th the cost of X-SHiELD, according to the vendor. [a7]
5. Artemis Security launched Orion-1, an AI model it says autonomously investigates and responds to corporate network attacks, outperforming Claude Opus 5.5 and GPT-6 Sol on its own benchmark. [a8]
```
Grounding: 1: S; 2: S; 3: S; 4: S*; 'Ai2' as maker inferred from 'our ... Ai2 Climate Emulator'; 5: S.

**deepseek-flash** - ledger $0.0011, list $0.0011; attempts: 2054/407 tok ok

```text
1. Google Cloud announced that its new frontier model, Gemini 4 Argon, is available on Google Cloud for complex, multi-step business work, covered by 3 outlets. [a1,a2,a3]
2. Google says Argon launches at an introductory rate of $2 per million input tokens and $10 per million output tokens through November 30, 2026. [a1]
3. The FBI alleged that OpenAI engineer Abdulrahman Alfozan hid a recording device in a restricted executive conference room to spy on the company, covered by 2 outlets. [a4,a5]
4. Grok Voice 3.0 is claimed to rank first on Artificial Analysis's Speech-to-Speech Index with a score of 86.9, according to x.ai. [a6]
5. Artemis Security launched Orion-1, an AI model it says autonomously investigates and responds to corporate network attacks, outperforming Claude Opus 5.5 and GPT-6 Sol on its own benchmark. [a8]
```
Grounding: 1: S; 2: S; 3: S; 4: S; 5: S.

### 2026-10-15 (92 items; packet 9886 bytes)

**deepseek-v4-pro** - ledger $0.0122, list $0.0115; attempts: 3085/495 tok quote_schema, 3102/522 tok ok

```text
1. Meta released Muse Spark Open, an open-weight frontier multimodal mixture-of-experts model for agentic coding that accepts images, audio, and video alongside text, covered by 9 outlets. [a1,a2,a3]
2. NVIDIA released Nemotron 3.5 Super VL, an open 120-billion-parameter multimodal model for enterprise agents, plus two edge Bolt models, covered by 3 outlets. [a4,a5,a6]
3. Black Forest Labs released FLUX 3 Image Klein, a 5.6-billion-parameter open-weights model for text-to-image generation, image editing, and generation with up to ten reference images, covered by 3 outlets. [a7,a8,a9]
4. Google's Gemini 4 Argon reportedly leads GPT 6 Astra on several legal, financial, and business benchmarks, though Astra leads selected software engineering and computer-use evaluations, covered by 2 outlets. [a10,a11,a12]
5. Volvo plans to launch hands-free, point-to-point driving by 2030 using Nvidia's AI technology, covered by 2 outlets. [a13,a14]
```
Grounding: 1: S; 2: S; 3: S; 4: S; sourced from the emergent.sh SEO comparison story; 5: S.

**deepseek-flash** - ledger $0.0026, list $0.0025; attempts: 3088/316 tok quote_not_found, 3106/313 tok ok

```text
1. Meta released Muse Spark Open, an open-weight frontier multimodal mixture-of-experts model for agentic coding that accepts images, audio, and video alongside text, covered by 9 outlets. [a1]
2. NVIDIA released Nemotron 3.5 Super VL, an open 120-billion-parameter multimodal model for enterprise agents, plus two smaller Bolt variants for local hardware, covered by 3 outlets. [a4,a6]
3. Black Forest Labs released FLUX 3 Image Klein, a 5.6-billion-parameter open-weights image model that runs on consumer GPUs with 8 GB of VRAM, covered by 3 outlets. [a9]
4. Volvo will use three pieces of Nvidia hardware and software in future vehicles for hands-free automated driving, according to the companies, covered by 2 outlets. [a14]
```
Grounding: 1: S; 2: S; 3: S; 4: S.

### 2026-10-16 (58 items; packet 7661 bytes)

**deepseek-v4-pro** - ledger $0.0051, list $0.0048; attempts: 2438/479 tok ok

```text
1. Reflection AI released Beam, a 501-billion-parameter open model with day-0 support in transformers, SGLang, and vLLM, covered by 4 outlets. [a1,a2,a3]
2. Meta released Muse Spark Open, an open-weight 816B-parameter multimodal model that can run locally on Mac Studios, covered by 2 outlets. [a4,a5]
3. Microsoft's Surface Laptop Ultra is reviewed as a true MacBook Pro competitor for Windows, though battery life falls short, covered by 2 outlets. [a6,a7]
4. NVIDIA's RTX Spark laptops show mixed performance, with fast local AI but unimpressive gaming due to weak single-threaded performance, covered by 2 outlets. [a8,a9]
5. OpenAI says GPT-Live-1.1 adds new voices and better accents to Voice in ChatGPT, Codex, and dots, rolling out today to all users. [a10]
```
Grounding: 1: S; 2: S; 3: S; 4: S; 5: S.

**deepseek-flash** - ledger $0.0012, list $0.0012; attempts: 2441/414 tok ok

```text
1. Reflection released Beam, a 501-billion-parameter open model it says finishes tasks in fewer tokens to lower cost per task, covered by 4 outlets. [a1,a2,a3]
2. Meta released Muse Spark Open, an open-weight 816B-parameter multimodal model, and worked with Apple so it could run locally on Mac Studios, Meta says. [a4,a5]
3. WIRED rates the Microsoft Surface Laptop Ultra 7/10, calling it a true MacBook Pro competitor for Windows hampered by battery life. [a6,a7]
4. Microsoft says MAI-Base-2 is an MoE foundation model with 80 billion active and 2.8 trillion total parameters. [a12]
5. Elorian released its first model, Glimpse, as a research preview with API access and a waitlist-only chat interface. [a11]
```
Grounding: 1: S; 2: S; 3: S; 4: S; 5: S.

### 2026-10-17 (14 items, quiet; packet 5012 bytes)

**deepseek-v4-pro** - ledger $0.0024, list $0.0021; attempts: 1498/105 tok ok

```text
1. Deepseek has released Deepseek-V4.1-Flash-1017 on its platforms and as an open-weight model on Hugging Face and ModelScope. [a1]
```
Grounding: 1: S.

**deepseek-flash** - ledger $0.0006, list $0.0006; attempts: 1501/161 tok ok

```text
1. Deepseek says its Deepseek-V4.1-Flash-1017 beats larger rivals like Claude Opus 5 and GPT 5.6-Sol on coding and agent benchmarks in internal tests. [a1]
2. Meta also released closed frontier models Muse Wonder and Muse Wonder Full, which the author says rank only behind Anthropic's Opus 5.5 on traditional benchmarks. [a2]
```
Grounding: 1: S; 2: S but stale: newsletter recap of the 10-12 release.

### 2026-10-18 (14 items, quiet; packet 4627 bytes)

**deepseek-v4-pro** - ledger $0.0026, list $0.0022; attempts: 1407/178 tok ok

```text
1. Anthropic has granted external evaluators employee-like access to assess its models' risks, with METR embedding a team in its office. [a2]
2. Anthropic announced a public benefit fund committing 5% of its shares, with an option to add 2% for every 50% value increase. [a8]
```
Grounding: 1: S; 2: S.

**deepseek-flash** - ledger $0.0006, list $0.0006; attempts: 1410/156 tok ok

```text
1. Anthropic says its AI agents logged six times as many work hours as human employees by August 2026, and it cites growing agent capability as the reason for fewer junior technical hires. [a11]
2. Anthropic announced a public benefit fund committing 5% of its shares, with an option to add 2% for every 50% value increase. [a8]
```
Grounding: 1: S; 2: S.

### Summary

| Day | Pro sentences / supported | Pro ledger $ | Flash sentences / supported | Flash ledger $ |
| --- | --- | --- | --- | --- |
| 10-12 | 5 / 5 | 0.0046 | 4 / 4 | 0.0010 |
| 10-13 | 5 / 5 | 0.0053 | 5 / 5 | 0.0014 |
| 10-14 | 5 / 5 (1 inferred vendor) | 0.0101 (recovery) | 5 / 5 | 0.0011 |
| 10-15 | 5 / 5 (1 SEO-sourced) | 0.0122 (recovery) | 4 / 4 | 0.0026 (recovery) |
| 10-16 | 5 / 5 | 0.0051 | 5 / 5 | 0.0012 |
| 10-17 (quiet) | 1 / 1 | 0.0024 | 2 / 2 (1 stale recap) | 0.0006 |
| 10-18 (quiet) | 2 / 2 | 0.0026 | 2 / 2 | 0.0006 |
| **Total** | **28 / 28** | **0.0423 (mean 0.0060)** | **27 / 27** | **0.0085 (mean 0.0012)** |

- No invented name, number or quote in 55 sentences (the validator enforces this; the manual check found
  none it let through). List prices (cache hits at the hit price) were 3-12% below the ledger figures.
- First attempts rejected: pro 10-14 (`sentence_count`, 6 sentences), pro 10-15 (`quote_schema`, quote
  over 40 words), flash 10-15 (`quote_not_found`, paraphrased quote); each recovery passed.
- Comparison: pro copies whole summary sentences more often and picks the multi-outlet stories, including
  reviews (10-16 Surface, RTX Spark) and the SEO comparison story (10-15); flash adds the outlet count
  more consistently and on 10-16 picked New releases (MAI-Base-2, Glimpse) over reviews. Flash's one
  defect is a stale recap (10-17 #2: a newsletter recap of Meta's 10-12 release presented as news).
  Quality is close; pro costs about 5x more and stays far under the $0.05/day bound.
- Not seen: instructions followed from article text, non-English output, URLs, truncation.

## 3. One-liners, noise rules and quiet days (deterministic, $0)

**One-liners** (40 New items on the 7 days): 15 from a digest-summary sentence, 25 from the novelty quote.
The spec rule (first summary sentence) does not name the item for 15 of 40 items and describes something
else for 5 (SemIf: "AWS cautions that the measurements include network latency ...", Game Finder,
Nemotron 3.5 Bolt, Satlyt, Joule Assistants). Spot check of all 40 under the plan rule: none invented,
none about another subject; weakest lines are short quote fragments ("SAP's new and expanded Joule
Assistants", "LendRecoup is Pareto efficient and credit fair").

**2026-10-16 as it would render** (pro brief; D3 list; folding; chips):

```text
DAILY AI SIGNALS
IN BRIEF
  Reflection AI released Beam, a 501-billion-parameter open model with day-0 support in
  transformers, SGLang, and vLLM, covered by 4 outlets. [1][2][3]
  Meta released Muse Spark Open, an open-weight 816B-parameter multimodal model that can run
  locally on Mac Studios, covered by 2 outlets. [1][2]
  Microsoft's Surface Laptop Ultra is reviewed as a true MacBook Pro competitor for Windows,
  though battery life falls short, covered by 2 outlets. [1][2]
  NVIDIA's RTX Spark laptops show mixed performance, with fast local AI but unimpressive gaming
  due to weak single-threaded performance, covered by 2 outlets. [1][2]
  OpenAI says GPT-Live-1.1 adds new voices and better accents to Voice in ChatGPT, Codex, and
  dots, rolling out today to all users. [1]
  Written by AI from the linked articles; check the sources.
[10 model releases] [9 product launches] [1 partnership] [1 hardware] [3 regulation & policy]
[1 legal] [4 security incidents] [1 people move]  +22 more
NEW                                       (all single source today: muted, no badges)
  GPT-Live-1.1                  model . OpenAI . via threadreaderapp.com
    "GPT-Live-1.1 brings these updates to Voice in ChatGPT, Codex, and dots"
  Glimpse                       model . Elorian . via techcrunch.com
    Elorian released its first model, Glimpse, as a research preview with API access and a
    waitlist-only chat interface.
  MAI-Base-2                    model . Microsoft . via microsoft.ai
    Microsoft says MAI-Base-2 is an MoE foundation model with 80 billion active and 2.8 trillion
    total parameters.
  d1-ultra                      model . Liquid AI . via liquid.ai
    "Today, we release d1-ultra, our new multimodal decision model"
  Nemotron-pretraining-Indic-v1 dataset . NVIDIA . via huggingface.co
    "We're excited to introduce Nemotron-pretraining-Indic-v1 approximately 2.8 trillion tokens
    across 22 Indian languages, releasing soon"
  Handwired                     technology . via x.com
    Cheng Lou introduced Handwired, a toy project that turns regular JavaScript code into a neural
    net with no training, exact outputs, and...
  Evidence Desk                 product . via towardsdatascience.com
    "Evidence Desk is a browser tool I built with Codex."
TOP STORIES
  Introducing Reflection Beam: an open-weight model for agentic coding on AWS
    4 outlets . spike: Beam, Reflection
  Muse Spark Open                                   2 outlets
  Microsoft Surface Laptop Ultra Review: The First Real AI PC
    2 outlets . spike: Surface Laptop Ultra
  NVIDIA RTX Spark and Kilo by Anaconda: New Device to Put Local AI to Work
    2 outlets . spike: RTX Spark
SPIKES  (empty after folding -> card hidden)
```

Against SC-003: no `variant of GPT` (single generic family token), no `variant of NVIDIA Nemotron` on the
dataset (vendor-stripped "Nemotron" is a family word; the plan also requires the same entity type), no
separate Beam/Reflection spikes, no `early signal` badge. Spikes on 10-16: Beam, Reflection -> Beam
story; RTX Spark, Surface Laptop Ultra -> their stories; Hugging Face and DeepSeek -> dropped as diffuse
(each link in a different story). 10-15: Black Forest Labs -> FLUX story; NVIDIA, Google DeepMind, Apple
-> diffuse (approximation: NVIDIA has 7 articles but only 3 links here; the code decides on all 7);
GPT-6 Astra and Gemini 3.8 Flash stay as spikes (GPT-6 Astra is not named by the comparison story it
shares links with).

**2026-10-18 quiet-day block** (14 items, no multi-publisher story, no New):

```text
DAILY AI SIGNALS
IN BRIEF
  Quiet day: 14 items, no story covered by more than one outlet.
  Anthropic has granted external evaluators employee-like access to assess its models' risks,
  with METR embedding a team in its office. [1]
  Anthropic announced a public benefit fund committing 5% of its shares, with an option to add 2%
  for every 50% value increase. [1]
  Written by AI from the linked articles; check the sources.
[1 product launch] [1 acquisition] [2 partnerships] [1 regulation & policy] [1 legal]  +8 more
```

10-17 is the same shape plus one New item (Deepseek-V4.1-Flash-1017, "variant of DeepSeek-V4.1-Flash"
kept: specific earlier entity).

## 4. Open points

1. The validator is syntactic; meaning was checked by hand on 55 sentences only. Implementation
   validation (tasks T5.2) repeats the manual check on the live code path.
2. SEO comparison pages (emergent.sh) can reach the brief as a "2 outlets" story (006 follow-up).
3. Quiet-day input includes newsletter recaps; flash used one as news. Pro did not; watch it.
4. Folding/diffuse figures above are approximations from at most 3 links per item.

## 5. Revision 2 re-measure: prompt `daily-signals-brief-2` (2026-10-19)

**Scope**: `deepseek-v4-pro` only, 2026-10-13, 10-15, 10-16, same packets as section 2. **Spend**: 6
calls, ledger $0.0332 of the $0.05 cap (run A $0.0167, run B $0.0165). Script
`tmp/007-brief-dryrun/rev2.py`; answers `report-rev2a.json` (A), `report-rev2.json` (B).

- Run A: ordering by event type as in the coordinator's R1. 10-15 dropped the SEO sentence; 10-13 split
  Gemini 4 Argon into two sentences (rollout, then availability) and dropped the Google Play story.
- Run B (plan text): run A plus "At most one sentence per story or item." and validation rule 9
  (`same_story`). All three passed on the first attempt. Reported below.

### 2026-10-13 (ledger $0.0052; 2,784 / 378 tokens)

```text
1. Google began a wide rollout of Gemini 4 Argon to paying users, with lower-tier plans lacking full access, covered by 6 outlets. [a1,a2,a3]
2. Meta introduced the Muse Wonder series, comprising Muse Wonder and Muse Wonder Full, as its most capable models for personal and professional agentic tasks. [a5,a6]
3. An OpenAI engineer was arrested after the company said it discovered a sophisticated recording device hidden in one of its offices. [a7,a8,a9]
4. Rivian partner Mind Robotics hired Doug Field as president to lead its robotics effort, according to the startup. [a10,a11]
```
Grounding: 1-4: S. Diff against revision 1: sentences 1-4 identical in substance; revision 1's sentence 5
(Google Play private vibe-coded apps, 2 outlets, product launch) is gone; the brief has 4 sentences.

### 2026-10-15 (ledger $0.0061; 3,137 / 489 tokens)

```text
1. Meta released Muse Spark Open, an open-weight frontier multimodal mixture-of-experts model for agentic coding, covered by 9 outlets. [a1,a2,a3]
2. NVIDIA released Nemotron 3.5 Super VL, an open 120-billion-parameter model, plus two edge Bolt models, with Bolt E4B due Oct. 23. [a4,a5,a6]
3. Black Forest Labs released FLUX 3 Image Klein, a 5.6-billion-parameter open-weights model for text-to-image generation, image editing, and generation with up to ten reference images. [a7,a8,a9]
4. Volvo will use Nvidia's tech for hands-free, point-to-point driving, according to the source. [a13,a14]
5. Google pitches Gemini 4 Argon as a single model for robot control, simulation building, and training-data evaluation, though demos still need heavy human prompting. [a10,a11,a12]
```
Grounding: 1-5: S; 4 copies the digest's vague "according to the source". Diff: revision 1's sentence 4
(Argon vs GPT 6 Astra benchmarks, from the emergent.sh comparison page) is replaced by sentence 5,
taken from the news article (The Decoder) in the same story; the SEO pages are still cited as ids
but carry no claim. Order otherwise unchanged; no release lost.

### 2026-10-16 (ledger $0.0052; 2,490 / 487 tokens)

```text
1. Reflection AI released Beam, a 501-billion-parameter open model with day-0 support in transformers, SGLang, and vLLM, covered by 4 outlets. [a1,a2,a3]
2. Meta released Muse Spark Open, an open-weight 816B-parameter multimodal model with a 1M-token context window, covered by 2 outlets. [a4,a5]
3. Microsoft launched the Surface Laptop Ultra, which WIRED rates 7/10 and calls a true MacBook Pro competitor for Windows hampered by battery life. [a6,a7]
4. NVIDIA's RTX Spark laptops are off to a good start, but reviewers say CPU-limited games perform poorly due to weak single-threaded performance and Windows translation overhead. [a8,a9]
5. OpenAI says GPT-Live-1.1 adds new voices and better accents to Voice in ChatGPT, Codex, and dots, rolling out today to all users. [a10]
```
Grounding: 1, 2, 4, 5: S. 3: "launched" is not stated in the cited text (the rest is); the validator
cannot catch a verb. Diff: same five events as revision 1; sentences 3-4 still cover the two
hardware-review stories, and the single-source releases (Glimpse, MAI-Base-2, d1-ultra) are still
left out. The model reads launch-day reviews as launches: both stories are `product_launch` in the
snapshot and nothing in the packet marks them as reviews. Option O1 (plan, "Brief") would mark the
Surface story (1 of 2 titles says "Review") but not the RTX Spark story.

### Result

| Day | Revision 1 | Revision 2 | Lost |
| --- | --- | --- | --- |
| 10-13 | 5 sentences | 4 (Play private apps dropped) | a 2-outlet product launch |
| 10-15 | SEO comparison claim as #4 | gone; robotics news from the same story | none |
| 10-16 | 2 review sentences | 2 review sentences (reworded; one unsupported "launched") | none; New releases still not chosen |

Cost unchanged: brief-2 adds 52 input tokens; mean $0.0055 per day on these 3 days, the same as revision
1's first attempts ($0.0051-0.0060); no recovery was needed.

## 6. Implementation validation (T5.2, 2026-10-19)

**Code**: branch `feat/007-daily-signals-brief` (Checkpoint 2 working tree, prompt
`daily-signals-brief-3`, methodology `daily-signals-3`). **Spend**: 9 paid runs, ledger $0.0497 of
the $0.50 cap: briefs $0.0388 (10 calls), extraction $0.0110 (29 calls, 10-17/18 only). Dump:
`tmp/007-brief-validate/dump.txt` (worktree, not committed).

Method: scratch copy of the 006 section 10 database (`ai_news-prodwindow.db`: local articles, public
digests 2026-08-03..10-16) and its ledger (unchanged extraction requests replayed at $0); `alembic
upgrade head`; the 10-17/18 public digests from the T0.1 fixtures. The local database has no articles
for 10-17/18 (copy taken before them) and production was not touched, so those 28 articles were created
from the digest items (title + digest summary, no body; extraction input `title_summary`). Then
`--recompute-only --recompute-all` and one paid `daily-signals --report-date D --max-usd <remaining,
max 0.10>` per day 2026-10-10..18, oldest first.

### Briefs (prompt `daily-signals-brief-3`, `deepseek-v4-pro`)

| Day | Items / quiet | Sentences | Calls | Ledger $ | Notes |
| --- | --- | --- | --- | --- | --- |
| 10-10 | 7 / yes | 2 | 2 | 0.0053 | first answer 4 sentences on a quiet day (`sentence_count`), recovery ok |
| 10-11 | 1 / yes | 1 | 1 | 0.0010 | one opinion item (the only item) |
| 10-12 | 56 / no | 5 | 1 | 0.0048 | Muse Wonder, Claude police tip, Clef-omni, pplx-decider, Maia |
| 10-13 | 90 / no | 5 | 1 | 0.0054 | Argon, Muse Wonder, OpenAI arrest, Doug Field, Play private apps |
| 10-14 | 73 / no | 5 | 1 | 0.0046 | Argon on Cloud, OpenAI device, Deep Review, Orion-1, Grok Voice 3.0 |
| 10-15 | 92 / no | 5 | 1 | 0.0066 | Muse Spark Open, Nemotron Super VL, FLUX Klein, Anthropic revenue, Granite Switch |
| 10-16 | 58 / no | 5 | 1 | 0.0054 | Beam, Muse Spark Open, GPT-Live-1.1, Glimpse, MAI-Base-2 |
| 10-17 | 14 / yes | 1 | 1 | 0.0027 | Deepseek-V4.1-Flash-1017 |
| 10-18 | 14 / yes | 2 | 1 | 0.0029 | Anthropic benefit fund, Disney / Character.AI |

Grounding (same rubric as section 2, each sentence read against the full title and summary of every
cited article): 31 / 31 supported, no invented name, number or quote. Weak: 10-15 #5 "According to
Hugging Face, IBM released Granite Switch 4.1" attributes an IBM post to its host (huggingface.co);
10-11 #1 "The Verge describes" for "The author describes" (a Verge author); 10-12 #5 keeps the digest's
vague "according to the report".

### Success criteria

- **SC-001** (10-12..18): met. 28 sentences, all supported; quiet days 10-17 (1 sentence) and 10-18
  (2) open with the template line; no review or comparison sentence on any day.
- **SC-002**: met. 42 / 42 displayed New items have a one-liner (15 summary, 27 quote); none invented,
  none about another subject. Weakest lines: "llm-echo 0.5" (10-18, the quote is the bare name; the
  digest summary says "The llm-echo debug plugin's ..." without the version), "LendRecoup is Pareto
  efficient and credit fair" (10-14), the TheoPhysEval quote about the authors (10-15).
- **SC-003** (10-16): met. GPT-Live-1.1 has no `variant of`; Beam and Reflection fold into the Beam
  story, RTX Spark and Surface Laptop Ultra into their stories, DeepSeek dropped as diffuse; no Spikes
  card; no `early signal` badge.
- **SC-005**: met. Brief cost $0.0027-0.0066 per day on 10-12..18 (mean $0.0046), $0.0053 with a
  recovery (10-10); bound $0.05.

### O1 effect on 10-16

Revision 2 (no marker) chose the Surface Laptop Ultra review and the RTX Spark review story for
sentences 3-4. With the marker (Surface story `kind: review`; RTX Spark not marked) the brief keeps
Beam and Muse Spark Open and then covers GPT-Live-1.1, Glimpse and MAI-Base-2: both review stories
are gone, including the unmarked RTX Spark one, and three single-source releases take their place.
10-15: the marked "Gemini 4 Argon vs ..." comparison story is not used; Anthropic revenue and Granite
Switch fill the slots. Spikes on 10-15 keep GPT-6 Astra, Gemini 3.8 Flash and Google DeepMind with that
comparison story as their reason (the rule picks the largest story; it is not review-aware).

### Rendering (T4.3)

Local web on a copy of the scratch database with the 10-14 brief row removed: 10-16 (normal), 10-18
(quiet), 10-14 (missing brief) at 1280 px and 375 px; no horizontal overflow. Date switching
14->16->18->15->14 in the page: the client render equals the server render (identical inner HTML)
each time. One fix from the check: the "Rising needs two weeks..." note is not shown on quiet days.

**After the Checkpoint 2 fixes** (coordinator F1/F2): a one-liner that leaves fewer than 3 words
besides the item name is dropped. Of the 42 lines above only "llm-echo 0.5" (10-18) is affected, so
41 / 42 displayed items now have a line and llm-echo 0.5 shows its sources only; none of the 40
fixture expectations changes. Quiet days now show Top stories and Rising/Spikes cards when they have
items (no empty cards); on 10-12..18 no quiet day has either, so the screenshots are unchanged.
