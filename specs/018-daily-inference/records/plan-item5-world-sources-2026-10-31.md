# Plan: world news stream about AI in human life (spec 018, item 5)

Date: 2026-10-31. Author: research session (agent). (Update 2026-10-31: the owner set the world Jev budget to $0.10 per day; this text first said
$0.05.) Covers FR-014..FR-018 of
`specs/018-daily-inference/spec.md`. Nothing in the repo was changed; the sample and scripts live
in the scratchpad. Marks: **[found]** = measured or read from a source (link given), **[decided]**
= decided by the research session, to be reviewed.

## 1. Findings

### 1.1 Candidates checked

| Source | Verdict | Why |
| --- | --- | --- |
| GDELT 2.0 raw GKG files, 15 min (`http://data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.gkg.csv.zip` and `.translation.gkg.csv.zip`) | **Use** | Free, no API limit, 65 languages, title + URL + themes + time per article, no key. |
| GDELT DOC 2.0 API | Do not depend on it | From this machine: 3 x HTTP 429, 1 x HTTP 200 with body `{}` in 10 minutes, spaced 12-45 s. Max 250 records per query, so one query per language is needed. Its fields are better (url, title, seendate, domain, language, sourcecountry), so keep it as an optional second reader behind a switch if prod IP is not blocked. |
| Google News RSS search (`news.google.com/rss/search?...`) | Reject | robots.txt of news.google.com: `User-agent: *` `Disallow: /` (only `/topics/`, `/publications/`, `/stories/`, `/swg/`, `/home` allowed); our downloader obeys robots.txt. Links are opaque redirect ids. About 60 items per query. Terms forbid automated use. |
| Keyed news APIs (NewsAPI, GNews, MediaStack, Event Registry, Media Cloud) | Reject | Need an account or key; excluded by the task and by FR-014 ("free"). |
| Curated general-news RSS feeds (Guardian, NYT, BBC, Al Jazeera, France24, SCMP, The Hindu, Spiegel, Le Monde, El Pais, Rest of World, ...) | **Use as a small second layer, later** | Tested 17 feeds: 16 answered 200 (Euronews 404, DW RDF 0 items, NPR rss.php failed). 554 entries, 68 matched AI keywords (12%), all editorially strong. Fits the existing RSS ingestion (`sources.yaml`-like), but must not enter `articles` (FR-016). Only about 70 AI items/day from 17 feeds, so it is a complement, not the base. |

### 1.2 GDELT raw files: facts [found]

- Terms of use (https://www.gdeltproject.org/about.html, "Terms of Use"): "available for unlimited and
  unrestricted use for any academic, commercial, or governmental use of any kind without fee ...
  any use or redistribution of the data must include a citation to the GDELT Project and a link to
  this website (https://www.gdeltproject.org/)". So: automated daily use is allowed; we owe a credit.
- Columns used (GKG 2.1 tab separated): 4 URL, 3 source domain, 1 time (file time, 15 min),
  7 themes (`V2Themes`), 9 locations (`V2Locations`), 25 translation info (`srclc:<iso3>`),
  26 extras with `<PAGE_TITLE>` (HTML-entity encoded) and `<PAGE_PRECISEPUBTIMESTAMP>`.
  Every row of the 24 h sample had a title.
- The `translation.gkg` files hold non-English pages. **Titles stay in the source language**
  (only themes and entities are English), so the keyword filter must be multilingual.
- GDELT has **no AI theme**: 24 h of themes contain only `SOC_EMERGINGTECH`, `TECH_AUTOMATION`,
  `TECH_BIGDATA`, etc. A theme filter alone is useless; keywords on the title are the filter.
- No source-country field in GKG (the DOC API has `sourcecountry`). The country in the sample is
  the most frequent *mentioned* country (FIPS code) and is noisy. Use ccTLD as a hint only.
- Size per day: 96 + 96 files = 280 MB + 539 MB zipped (about 820 MB/day, 25 GB/month),
  2.7 GB unzipped, 210,479 rows; one Python pass with regex took 14 s on this machine.
- Freshness: newest file is 15-30 min old. At the time of the test the 3 newest translation files
  returned 404 on https (lastupdate lists them on http); the sample is therefore 23 h 15 min.
- `lastupdate.txt` and `masterfilelist.txt` (129 MB) exist; `masterfilelist.txt` should not be
  downloaded daily. File names are predictable (`%Y%m%d%H%M%S` on :00/:15/:30/:45), so build them.
  `lastupdate.txt` answers 301 to https on http, so use https.

## 2. The measured day (24 h ending 2026-10-31 ~21:30 UTC)

File: `scratchpad/world-sample-2026-10-31.jsonl` (2,315 lines; fields url, title, date, lang,
country, tld, source, match, kept).

| Step | Count |
| --- | --- |
| Rows read (GKG + translation GKG, 93 translation + 96 primary files) | 210,479 |
| Title matches the AI keyword list (strong 1,534 / weak 781 after dedup) | 2,896 raw |
| After dedup (same canonical URL, same first 60 normalized title chars) | **2,315** |
| After free filters (finance titles/themes/domains, our own source domains, weak words not AI) | **1,619** |
| Hosts in the 1,619 | 998 (long tail: top 20 hosts = 13%) |

Language of the 1,619: English 549 (34%), Spanish 184, Chinese 103, French 90, Russian 79,
Italian 77, Portuguese 70, Vietnamese 62, German 57, Turkish 34, Romanian 34, Arabic 31; 47
languages in all; 66% are not English. Country (mentioned, noisy): unknown 477, US 269, China 108,
India 91, Italy 43, UK 35, France 32, Germany 32, Vietnam 32, Brazil 29, Russia 26, Indonesia 25;
ccTLD present on 750 of 1,619 (76 distinct).

Share about AI in human life, hand judged on 50 random titles of the deduped set before the
filters (seed 7): **13 of 50 (26%)** (5 were false matches such as "Automatically", a name
"Alexa", 10%). After the filters, on a new random 50 (seed 11): **19 of 50 (38%)**, 4 more
borderline (46%), about 6 of 50 were "robot" but not AI. Everything else is industry, markets,
product launches, model news. So of 1,619 candidates a day about **600-750 are in scope**, most
of them repeats of the same events (the Pope's statement alone came as about 12 titles in 6
languages).

20 good examples (all from this day):

1. Pope Leo XIV: AI can never be a person - https://www.ewtnnews.com/vatican/pope-leo-xiv-ai-can-never-be-a-person-its-future-depends-on-our-choices
2. Howard County, Md., students need teacher permission to use AI - https://www.govtech.com/education/k-12/howard-county-md-students-need-teacher-permission-to-use-ai
3. Chief Justice turns attention to AI in Ghana's courts - https://www.ghanamma.com/2026/10/30/chief-justice-baffoe-bonnie-turns-attention-to-ai-in-major-development-for-ghanas-courts/
4. Smyth County urges Supreme Court to review AI-generated child sexual abuse ruling - https://wcyb.com/news/local/smyth-county-urges-supreme-court-to-review-ai-generated-child-sexual-abuse-ruling
5. Khanna govt school first in state to get an AI laboratory - https://www.hindustantimes.com/cities/chandigarh-news/khanna-govt-school-becomes-first-in-state-to-get-ai-laboratory-101793386072787.html
6. "Save the goats. No data center": Oklahoma farmers - https://www.lefigaro.fr/international/sauvez-les-chevres-pas-de-data-center-en-oklahoma-l-inquietude-et-l-impuissance-des-agriculteurs-face-aux-consequences-de-l-ia-20261029
7. Delhi Police deploy CCTV and AI surveillance for a rally - https://www.outlookindia.com/national/delhi-police-deploy-cctv-ai-surveillance-for-india-bloc-rally-at-ramlila-maidan
8. Philadelphia councilmember: tax sidewalk delivery robots - https://www.phillytrib.com/news/local_news/philadelphia-councilmember-tax-owners-of-sidewalk-delivery-robots-that-cost-human-jobs/article_5485a7ec-3798-4d9d-880a-7e63324254c2.html
9. Terminally ill professor Jan Rotmans has an "AI twin" made (NL) - https://nos.nl/artikel/2637407-ongeneeslijk-zieke-hoogleraar-jan-rotmans-laat-ai-tweeling-van-zichzelf-maken
10. Historians worried by AI-forged Nazi-era documents (DE) - https://www.badische-zeitung.de/mit-ki-gefaelschte-ns-zeitdokumente-besorgen-historiker
11. What can AI do in the cowshed? (DE) - https://www.topagrar.com/rind/news/was-kann-ki-im-kuhstall-20030571.html
12. AI drones trialled to monitor dingoes and livestock fencing in Victoria - https://www.thesheepsite.com/ai-drones-trialled-to-monitor-dingoes-and-livestock-fencing-in-victoria
13. Robot dogs to defend sheep from wolves (IT) - https://www.toscanamedianews.it/semproniano-cani-robot-per-difendere-le-pecore-dai-lupi.htm
14. Les Borges relaunches municipal AI, opposition questions the contract (CA) - https://www.segre.com/ca/comarques/261031/les-borges-rellanca-ia-municipal-i-l-oposicio-questiona-contracte_1382891.html
15. Woman says she has a relationship with an AI and wants legal rights (PT) - https://www.correiobraziliense.com.br/brasil/2026/10/7531216-mulher-diz-ter-relacionamento-com-ia-e-defende-reconhecimento-legal-de-direitos-em-sp.html
16. Psychologists warn about AI chatbots giving harmful mental health advice - https://www.lbc.co.uk/article/psychologists-warn-ai-chatbots-mental-health-5HjdkhB_2/
17. Grok and the Polish constitutional court dispute (PL) - https://natemat.pl/673780,grok-wkopal-nawrockiego-ws-chaosu-w-tk-ai-od-muska-nie-mialo-cienia-watpliwosci
18. Will the fight against AI data centres decide the US midterms? (DE) - https://kurier.at/politik/ausland/midterms-wahlen-usa-trump-ki-rechenzentren-protest/403201829
19. Does AI give us better literature? (DK radio debate) - https://www.dr.dk/lyd/p1/p1-debat/p1-debat-2026/giver-ai-os-bedre-litteratur-11162601435
20. App uses AI to check criminal records before a date (PT) - https://dol.com.br/noticias/brasil/967022/vai-sair-com-alguem-app-usa-ia-para-consultar-antecedentes-criminais

A harm case that ER-11 must catch: "Woman with epilepsy dies after following AI medical advice" -
https://noticias.r7.com/internacional/mulher-com-epilepsia-morre-apos-seguir-conselhos-medicos-de-inteligencia-artificial-31102026/

The owner's example ("an icon made with AI was consecrated") did not appear in this day, so it is
not proof either way; the stream is built for that class (faith, farms, courts, schools: see
examples 1, 6, 10-13).

## 3. Free filter [decided, measured on the sample]

Local keyword filter on the title (code in `scratchpad/kw.py`, `scratchpad/filt.py`):

1. **Strong match** (kept): phrase list in 30+ languages, case-insensitive: "artificial
   intelligence", "inteligencia/inteligência artificial", "intelligence artificielle", "künstliche
   Intelligenz", "intelligenza artificiale", "нейросет*", "искусственный интеллект", "штучний
   інтелект", "sztuczna inteligencja", "yapay zeka", "kecerdasan buatan", "trí tuệ nhân tạo",
   "人工智能", "人工智慧", "人工知能", "인공지능", "الذكاء الاصطناعي", "הבינה מלאכותית", Hindi, Bengali,
   Tamil, Thai, Greek, Czech, Romanian, Nordic, Hungarian, Croatian and others; brand terms
   (ChatGPT, OpenAI, DeepSeek, chatbot, deepfake, LLM, GPT-n); and the case-sensitive tokens
   `AI`, `ИИ`, `ШІ`, `GPT`, `AI-`.
2. **Weak match** (kept for Jev): `IA`, `KI` (Spanish/French/Portuguese/German short forms that
   collide with other words), "robot", "algorithm", "copilot", "grok", "anthropic". Weak without
   `IA`/`KI`/robot/algorithm is dropped. Names and substrings that gave false hits were removed
   ("automat*", "Alexa", "Siri", "Gemini", "Claude", `\w+-ai`, which also matched the name "Ai").
   All-caps titles do not count `AI` as strong.
3. **Drop**: titles with finance words (stock, shares, Nasdaq, valuation, earnings, Aktie, Börse,
   bolsa, 股, 基金, акции, ...), themes `ECON_STOCKMARKET`, `ECON_IPO`, `ECON_EARNINGSREPORT`,
   `ECON_WORLDCURRENCIES`, `ECON_BITCOIN`, `ECON_OILPRICE`, a small list of finance domains, and
   hosts of our own 106 source domains (they are in the digest already).

Effect: 2,315 -> 1,619 (-30%); on the labelled 50, 12 of 13 in-scope titles kept, the one lost was
removed by a domain I had put in the finance list by mistake (slguardian.org: remove it).
Known gap: own-domain match is exact host, so `arstechnica.com` was not matched against
`feeds.arstechnica.com`; match on the registrable domain (the tests in step 3 cover it).

Two ordering signals computed for free before Jev (to choose the top N of the day): event cluster
size (many outlets, same language) and human-life themes in `V2Themes` (`EDUCATION`,
`GENERAL_HEALTH`, `LEGISLATION`, `TRIAL`, `RELIGION`, `SOC_POINTSOFINTEREST_*`). Not measured
beyond reading the 100 titles; mark as tunable.

## 4. Cost per day [decided, arithmetic from the prompt prices]

Price: $0.042 per 1M input tokens, output priced 0 in `provider_costs.PRICES["jev"]`. Text limit:
16,000 characters (`CONTENT_LIMIT` in `src/app/core/jev.py`), about 4,000 tokens. Pages extracted in
the test were 2.1k-10.2k characters (10 pages, mean about 5k, about 1.4k tokens).

| Plan | Requests | Input tokens | $/day |
| --- | --- | --- | --- |
| All 1,619 with full text (worst) | 1,619 x 4.3k | 7.0M | 0.29 |
| All 1,619 with mean text, one question set | 1,619 x 1.7k | 2.75M | 0.116 |
| **Two steps (chosen)**: A) title + domain `ai_relevant` for all 1,619, B) FR-001 with text for the top 100 | 1,619 x 0.3k + 100 x 1.7k..4.3k | 0.66M..0.92M | **0.028..0.039** |

So about **$0.03-0.04 a day, $0.9-1.2 a month**, below the world-stream share of the $3/month
(FR-012). Without the title step the stream would break the $0.10/day Jev cap, so the cap forces
the two steps. The cap itself: **world Jev budget $0.10/day as its own line in the provider
journal** (not shared with the digest's $0.05), hard stop when reached.

Assumptions to verify in step 5: a title-only Jev request is about 300 tokens including the fixed
prompt; Jev accepts a request without content (title + domain only); candidates reaching B are
at most 100 per day.

## 5. Text for retelling (FR-005) [found by test]

- Robots.txt for the 20 biggest hosts of the filtered set, with our token `ai-news-collector`
  and the declared user agent: 20 of 20 answered (19 x 200, 1 x 404 = allow), **211 of 211** URLs
  allowed. One had `Crawl-delay: 600` (manilatimes.net), which `SourcePageDownloader` honours, so
  such a host is effectively skipped.
- 40 random hosts of the long tail: 38 allowed, 1 robots 404 (allowed), 1 robots 403 (denied by our
  rule): **39 of 40 allowed (97%)**. Expect about 3-5% of candidates to have no text.
- Extraction with the repo's `inspect_page` (`src/app/storage/article_evidence_cache.py`) on 10
  pages from 10 hosts in 7 languages (stltoday, abc.net.au, habersefi, kenh14, naturalnews,
  correiobraziliense, capital.ro, tribuneindia, newsmonkey.be, wyofile): **10 of 10 `extracted`**,
  no issues, 2.1k-10.2k characters. Paywalls will exist (`paywall` issue exists in the inspector);
  they fall back to the title-only story (spec User Story 1, scenario 4).
- Load: 100 pages/day plus robots.txt, `ARCHIVE_DOWNLOAD_CONCURRENCY` workers, 1 s per host. A few
  minutes a day. **Do not download the 1,619.**
- How: reuse the archive downloader and store the text as an `ArchiveDocument` /
  `origin = source_page` version via `archive_articles` with a transient `Article`
  (like `archive import-db`), so ER-9 ("archive texts are read, never published") and the
  no-web-import invariant of `capture.md` hold. Decided: do not invent a second crawler.

## 6. Plan

### 6.1 Design [decided unless marked found]

- **Source**: GDELT raw GKG, primary + translation files, 15 min each. DOC API: optional reader
  behind `WORLD_GDELT_DOC_ENABLED` (default off), because it is blocked here and capped at 250.
- **Schedule**: one systemd job `ai-news-daily-world` at **04:00 UTC** (after fetch 01:00, digest
  02:00, archive 03:00; bulletin at 05:00; deadline 06:00 UTC, SC-001). It processes the UTC day
  D-1 (files `D-1 00:00:00` to `D-1 23:45:00`). Once a day is enough: the bulletin is daily and the
  files are fixed after publication. A state row remembers processed file stamps, so a rerun or
  a catch-up after an outage skips what is done. Same shape as `run_daily_archive_job.sh`:
  host lock, release image, `timeout`, always exit 0, one log line.
- **Storage**: a separate table `world_candidates` (migration), never `articles`, so `/daily` and
  its sources are untouched (FR-016). Columns: `id`, `url_canonical_hash` unique (the same
  `canonicalize` as `articles`), `url`, `title`, `source_domain`, `language`, `country_hint`
  (ccTLD or mentioned country, nullable), `published_at`, `first_seen_at`, `gdelt_file`,
  `match_kind` (strong/weak), `cluster_key`, `priority`, `state` (`new`, `screened_out`,
  `screened_in`, `text_ready`, `no_text`, `assessed`, `failed`), `screen_confidence`,
  `attempts`, `last_error`. Second table `world_files` (`stamp`, `kind`, `state`, `rows`, `matched`,
  `error`). FR-001 answers (WorldChange) are keyed by `url_canonical_hash` (articles have none);
  item 1 of the order should accept either `article_id` or hash. Dedup: unique hash plus the
  within-day first-60-characters title key as `cluster_key` (a cluster has one representative
  sent to Jev, outlet count kept for ranking, FR-003).
- **Retention**: candidates older than 30 days are pruned; archive documents stay (spec 016).
- **Jev**: step A `ai_relevant` on title + domain + language, all filtered candidates; step B
  FR-001 four questions on `jev_state` text (separate request, `RUBRIC_VERSION` untouched), only
  for the top N=100 `screened_in` with text. Rank for B: confidence x outlet count, then
  human-life themes.
- **Failure handling**: a missing GKG file is retried in the same run (3 tries, 30 s), then marked
  `missing`; up to 8 missing files of 192 keep the day `ok`, more makes the day `partial`
  (spec: no bulletin for a partial day; the world stream is dropped from that day only, the
  digest bulletin goes out). Download outage uses the archive's outage rule. Jev failure: the
  existing `JevInputTooLarge` / transport-failure rules; no retry loop; unprocessed candidates
  stay for the next run for up to 2 days. A host without text goes to `no_text` and the story
  keeps the title only.
- **Cost cap**: Jev world line $0.10/day in the provider journal; at cap the stream stops and
  logs `world_cost_cap`. Cost report in the run summary line. GDELT itself costs nothing; 25 GB/month
  of download is the only resource.
- **Credit**: the page footer says "News discovery: GDELT Project (gdeltproject.org)" because the
  terms require a citation and a link. [decided; reader-visible, see open questions]
- **Check before use (FR-018)**: for the first days run with `--dry-run` / `bulletin: off`:
  record candidates/day, share accepted by A and B, cost/day, 20 sampled stories in
  `records/world-days-<date>.md`.

### 6.2 PR-sized steps (each: code doc `src/app/core/world/world.md` first, then code and tests;
review by a different session)

1. **W1 doc + keyword filter (no network)**. `world.md` (Behavior, Decisions, Invariants), module
   `world/filter.py` with the keyword lists and drop rules from section 3. Tests:
   `test_filter_strong_phrases_in_many_languages`, `test_filter_weak_requires_ia_ki_or_robot`,
   `test_filter_drops_finance_titles_and_themes`, `test_filter_drops_own_registrable_domains`,
   `test_filter_ignores_names_alexa_ai_and_automatically`, plus a small fixture of 60 real titles
   from the sample (30 in, 30 out).
2. **W2 GKG reader (no database)**. `world/gdelt.py`: file name builder for a UTC day, streamed
   download (httpx, bot user agent, https, 2 files at a time, 1 s apart), unzip stream, parse
   rows, decode title, language from `srclc`, ccTLD, cluster key; `ai-news world scan --date
   --dry-run` prints counts. Tests with a 20-line GKG fixture and a fake transport: `test_gkg_row_parse_title_and_lang`,
   `test_missing_file_counts_as_missing`, `test_day_file_names_cover_96_stamps`, `test_scan_dry_run_writes_nothing`.
3. **W3 storage + migration**. `world_candidates`, `world_files`; repo with upsert by hash,
   prune, state transitions. Tests: `test_world_candidate_dedup_by_canonical_hash`,
   `test_world_prune_keeps_archive`, migration round trip like `test_article_archive_migration_round_trip`,
   `test_world_tables_not_read_by_digest` (no import from web/digest).
4. **W4 `ai-news world collect` + job script**. Wires W2+W3, state of processed files, summary log
   line `world_collect_finished` (files, rows, matched, kept, new, missing, partial), systemd unit
   and timer 04:00 UTC, `run_daily_world_job.sh` like the archive one. Tests:
   `test_collect_resumes_without_reprocessing_files`, `test_collect_partial_day_flag`,
   `test_world_job_script_is_isolated`, `test_install_timers_includes_world`.
5. **W5 Jev steps A and B**. `ai_relevant` title screen and FR-001 (item 1's questions) for
   candidates, daily cap line in the provider journal, ranking and N=100. Tests: `test_screen_sends_title_and_domain_only`,
   `test_stage_b_only_for_top_n_with_text`, `test_world_cap_stops_requests`,
   `test_world_jev_failure_leaves_candidates_pending`. Gate: measure the real token sizes of A and B
   on one stored day and write them into `records/` (replaces my assumptions of section 4).
6. **W6 text download via the archive**. Uses `SourcePageDownloader` with a transient `Article`;
   `no_text` states; paywall and robots outcomes. Tests: `test_world_text_goes_through_archive_robots_and_bot_agent`,
   `test_world_text_blocked_by_robots_is_no_text`, `test_world_never_downloads_more_than_n`.
7. **W7 first days check (FR-018)**. `records/world-days-<date>.md` with candidates, accepted
   share, cost, sample; owner switch `WORLD_STREAM_IN_BULLETIN` (default off) read by the bulletin
   builder (item 2/4). No code beyond the switch.
8. **W8 (optional, later)**. Curated general RSS layer (Guardian AI tag, NYT, BBC, Al Jazeera,
   SCMP, The Hindu, Spiegel, Le Monde, El Pais, Rest of World) as candidates of the same table
   (`source_kind = rss`); and the DOC API reader if prod IP is not blocked.

Dependencies: W1-W4 need nothing from items 1-4; W5 needs the item 1 questions; W7 needs the
builder (item 2).

## 7. Risks

- **Quality**: only 38-46% of filtered titles are in scope and the same event arrives many times;
  Jev A plus clustering must cut this. Not measured: Jev precision on these titles (W5 gate).
- **Blocking / availability**: raw files have no rate limit but depend on one project (GDELT);
  the DOC API blocked this machine (429); a day with many missing files makes the stream
  `partial`. Mitigation: the optional RSS layer (W8).
- **Bandwidth**: about 820 MB zipped per day (25 GB/month). Prod VPS limit is unknown (no ssh).
  If too heavy, reduce to the 48 primary files plus the translation files of the 6 biggest
  languages; measure on prod in W4.
- **Terms**: GDELT data is free, requires citation (footer). Retelling follows ER-9. Publisher
  copyright is unaffected by GDELT's licence; we publish own retelling + link only.
- **Languages**: 47 languages in a day; the model must translate and ground names/numbers (FR-005)
  across scripts: the grounding check by character match may fail on transliterated names.
  Check on non-Latin stories in item 3.
- **Harm and sensitivity** (ER-11): the stream brings accidents and abuse (see the epilepsy
  case); item 1 `harm_to_people` must be tested on world titles in the FR-002 check.
- **Country field** is weak (no source country in GKG); do not show it to readers.

## 8. Questions

Settled:
- Which source: GDELT raw GKG [found, measured]. DOC API not as base [found: 429].
- Google News RSS: rejected [found: robots.txt `Disallow: /`].
- Two-step Jev with a title screen [decided: forced by the $0.10/day cap, section 4].
- Separate tables, text through the archive [decided: FR-016, ER-9, capture.md].
- Job time 04:00 UTC and once a day [decided].
- Citation of GDELT in the footer [decided: required by the terms; it adds one line readers see,
  noted for the owner but not a blocker].

For the owner (money or what readers see), none is a hard blocker:
1. Is the footer line "News discovery: GDELT Project" acceptable? Recommendation: yes (terms
   require it).
2. Is a separate Jev budget of $0.10/day for the world stream (about $1-1.5/month, inside the
   approved $3) acceptable? Recommendation: yes.
