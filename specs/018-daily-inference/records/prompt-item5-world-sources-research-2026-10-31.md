# Prompt: world news sources about AI in human life, research and plan (spec 018, item 5, 2026-10-31)

You research and plan how `ai-news-collector` collects general world news about AI in human life
(courts, schools, churches, farms, city halls, hospitals, any country, any language). Example the
owner gave: "in Belarus an icon made with AI was consecrated". Our 152 current sources are AI and
tech outlets and miss such stories. **No changes to the repo, no commits, no production access
(no ssh), no paid calls, no accounts or API keys.** Free public endpoints only. Report in English.

## Read first

From `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (read without touching the working tree):
- `git show origin/master:specs/018-daily-inference/spec.md`: The idea, ER-*, FR-001, FR-003,
  FR-014..FR-018, FR-012.
- `git show origin/master:specs/018-daily-inference/voice.md`: Areas.
- `git show origin/master:src/app/core/archive/capture.md`: how we download pages politely
  (robots.txt, declared bot user agent, per-host pacing) - reuse it, do not invent another crawler.
- `git show origin/master:src/app/core/ingestion/pipeline.md`: how articles enter the system now.

## Known so far

- GDELT DOC 2.0 API (`https://api.gdeltproject.org/api/v2/doc/doc?query=...&mode=artlist&format=json&timespan=1d&maxrecords=250`)
  answers HTTP 429 "Please limit requests to one every 5 seconds" - from this machine it answered
  429 even after a 20 s pause at about 22:40 UTC on 2026-10-31 (the coordinator had sent several
  quick requests). Wait several minutes before your first request and keep at least 10 s between
  requests; if it stays blocked, say so and use the other options.
- GDELT also publishes raw 15-minute files (`http://data.gdeltproject.org/gdeltv2/lastupdate.txt`,
  GKG with themes, URLs and page titles in extras) without that API limit.

## Steps

1. **Candidates.** Check at least: GDELT DOC API (queries for AI in several languages, e.g.
   "artificial intelligence", "нейросеть", "искусственный интеллект", "inteligencia artificial",
   "intelligence artificielle", "KI"/"künstliche Intelligenz", "人工智能"; or `sourcelang:`/theme
   filters), GDELT raw GKG files (AI-related themes), Google News RSS search feeds, and any other
   free source you find. For each: terms of use for our case (automated, daily, retell with link),
   limits, languages, freshness, what fields we get (title, url, date, language, country, text?).
2. **Measure one real day.** For the best one or two sources, collect the last 24 hours of
   AI-related articles into
   `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/8230bf51-ec40-4f65-b975-34c791a2cee9/scratchpad/world-sample-2026-10-31.jsonl`
   (url, title, date, language, country, source). Give: total, after dedup (same url / near-same
   title), by language and country, share that is about AI in human life rather than the AI
   industry (judge a random sample of 50 titles by hand), and 20 good example titles with links.
3. **Free filters.** Propose the query set and a local keyword filter (languages, ambiguous "AI"
   matches) and measure on the sample how many candidates per day would reach Jev; estimate Jev
   cost with $0.042 per 1M input tokens and the 16,000-character text limit of `jev_state`.
4. **Text.** How we get article text for retelling (FR-005): the archive downloader on our own
   bot user agent; estimate how many of the sample pages allow it (check robots.txt for the top 20
   hosts; do not download article pages in bulk, at most 10 pages to test extraction).
5. **Plan.** Write `specs/018-daily-inference/records/plan-item5-world-sources-2026-10-31.md`
   **in the scratchpad** (path:
   `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/8230bf51-ec40-4f65-b975-34c791a2cee9/scratchpad/plan-item5-world-sources-2026-10-31.md`;
   the coordinator moves it into the repo): chosen sources and queries, schedule (once or several
   times a day, within the limits), storage (a separate table so the digest at `/daily` keeps its
   sources, FR-016; dedup by canonical URL hash like `articles`), filters, text download, Jev step
   (FR-001 questions, separate request), failure handling, cost cap, and a list of PR-sized steps
   with tests. Mark every choice as found (with source link) or decided by you.

## Report (final message)

Short: the recommended source(s) and why; the day's numbers; 10 example titles; expected candidates
and cost per day; risks (terms of use, blocking, languages); open questions, each settled (found /
decided) or a yes/no for the owner only if it is about money or what readers see.
