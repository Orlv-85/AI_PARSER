# Research: How News Products Present a Daily Brief and Unverified Items

**Feature**: `007-daily-signals-brief` | **Date**: 2026-10-19 | **Used by**: `plan.md`

## Findings (sourced)

1. **Lead with one-sentence facts; context only when earned.** Axios "Smart Brevity": key information
   in single subject-verb-object sentences, scannable formats, "Why it matters" in one sentence at most
   ([journalism.co.uk](https://journalism.co.uk/news/how-axios-is-reinventing-text-journalism-with-smart-brevity-/s2/a966845),
   [notes on the book](https://mickmel.substack.com/p/notes-from-smart-brevity-from-jim)). AI dailies
   (TLDR AI, Ben's Bites, The Batch) use the same shape: a headline plus a one- or two-line "what it is"
   per item, about a 5-minute read ([daily.dev review of TLDR](https://daily.dev/blog/tldr-newsletter-review-worth-subscribing/)).
2. **One event = one entry; the rest folds under it.** Techmeme clusters coverage of one story under one
   headline, with other outlets folded as "More:" links; editors remove duplicates
   ([Wikipedia](https://en.wikipedia.org/wiki/Techmeme),
   [TechCrunch 2011](https://techcrunch.com/2011/10/31/techmeme-opens-the-kimono-on-how-it-chooses-headlines-and-sources/amp/)).
   Google News groups results by story using entity understanding
   ([9to5Google](https://9to5google.com/2021/03/08/google-search-full-coverage/)).
3. **Coverage count is a signal readers understand.** Ground News merges articles about one event into a
   story and shows how many sources covered it ([Wikipedia](https://en.wikipedia.org/wiki/Ground_News),
   [Blindspot](https://about.ground.news/blindspot)).
4. **Single source = attribute, do not badge.** AP seeks more than one source and requires attribution
   of anything not confirmed by its own reporting; one authoritative source can suffice
   ([AP: anonymous sources](https://ds.svcs.associatedpress.com/behind-the-news/when-is-it-ok-to-use-anonymous-sources)).
   Reuters writes "could not immediately verify" rather than a label
   ([Reuters Handbook](https://www.mediareform.org.uk/wp-content/uploads/2015/12/Reuters_Handbook_of_Journalism.pdf)).
   In our data most single-source New items are the vendor's own post (`liquid.ai`, `microsoft.ai`,
   `x.ai`): authoritative for "they announced X", not for their claims.
5. **LLM summaries of news fail mostly on sourcing.** EBU/BBC study (3,000+ answers, 22 broadcasters):
   45% had a significant issue, 31% sourcing problems, 20% accuracy problems, and "ceremonial
   citations" that look rigorous but do not support the claim
   ([Computerworld](https://www.computerworld.com/article/4077344/ai-chatbots-are-wrong-about-news-45-of-the-time.html),
   [EBU report](https://www.mediaguru.cz/media/xfhplvup/report_ebu-mis-bbc.pdf)).
6. **Label machine summaries and keep them visually distinct.** After the BBC complaint, Apple paused
   news notification summaries and brought them back italicised with a beta/error notice
   ([Tom's Guide](https://www.tomsguide.com/ai/apple-intelligence/apple-scraps-apple-intelligence-news-feature-after-misinformation-complaints-what-you-need-to-know),
   [Silicon Republic](https://www.siliconrepublic.com/business/apple-halt-ai-notification-summaries-backlash-features)).

## Recommendations per spec item

| Spec item | Practice adopted | Why |
| --- | --- | --- |
| Brief shape (US1) | 3-5 one-event sentences, most covered first; each sentence links its sources (small numbered links); single-source facts attributed in the text ("Microsoft says"); heading "In brief" plus a muted line "Written by AI from the linked articles; check the sources." | Smart Brevity (1); sourcing is where LLM summaries fail (5); visible AI label (6) |
| Grounding | Every sentence cites article ids and an exact quote; app-side checks reject unknown ids, quotes not in the text, numbers and capitalized names absent from the cited text | Answers "ceremonial citations" (5) with a mechanical check, not a second model |
| One-liners (US2) | One line per New item: our own digest sentence that names the item and says what it is or that it launched; otherwise the source's own launch sentence, shown in quotes | TLDR-style "what it is" line (1); quotes mark source wording (4) |
| D3 confirmed vs single source | One list; confirmed first with "N outlets"; single-source items muted with "via publisher"; no badge, no headers (wireframe below) | Coverage count (3) + attribution instead of a warning badge (4) |
| Spike folding (US3) | A spike that is the same event as a shown story/New item becomes a tag on that item; a company spike spread over unrelated stories is dropped; a kept spike shows its biggest story as the reason | One event = one entry (2) |
| Chips (US3) | Hard event types only; analysis/research/other/benchmarks fold into "+N more" | Readers act on events, not on genre counts (1) |
| Quiet day (FR-006) | Say it plainly with counts, then at most 2 sentences and the New list; no empty cards | An empty frame reads as broken; a stated count is information (3) |

## D3: one option

Confirmed items (>= 2 publishers) first with their outlet count; single-source items follow in a muted
style with "via <publisher of the first link>" instead of the `early signal` badge. One list, the
existing 8-item cap and ordering (plan 006 Decision 5) unchanged, no section headers. This keeps the
coordinator's hypothesis and replaces "1 source" with attribution: "via liquid.ai" tells the reader both
that it is single-source and whether the source is the vendor itself.

```text
NEW
Muse Spark Open                         model . Meta . 9 outlets
  Meta trained Muse Spark Open for agentic coding, including reading a codebase, ...
  variant of Muse Spark                                      [sources]
Nemotron 3.5 Super VL                   model . NVIDIA . 3 outlets
  NVIDIA released Nemotron 3.5 Super VL, an open 120-billion-parameter model, ...
- - - - - - - - - - - - - - - - - - - - - - (muted below) - - - - - - - - - - -
d1-ultra                                model . Liquid AI . via liquid.ai
  "Today, we release d1-ultra, our new multimodal decision model"   [sources]
MAI-Base-2                              model . Microsoft . via microsoft.ai
  Microsoft says MAI-Base-2 is an MoE foundation model with 80 billion active ...
```

The dashed rule is a CSS top border on the first muted item, not a header. Rejected: two sections
("Confirmed" / "Single source"; on 3 of the 5 weekdays 10-12..16 the confirmed section would hold
0-1 items) and
a per-item "unconfirmed" label (reads as doubt about vendor posts that are authoritative for the
announcement itself).
