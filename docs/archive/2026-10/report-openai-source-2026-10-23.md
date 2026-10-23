# Report: why OpenAI news barely reach the site (2026-10-23)

Task: `docs/prompt-openai-source-investigation-2026-10-23.md`. Prod read-only (`ssh ai-news`,
`SELECT` only, log reads, one `curl` per URL); no writes, no restarts, no paid calls.
Admission runs since 2026-10-10, so "last 30 days" holds 13 daily runs.

## Root cause

Two causes stack:

1. **openai.com article pages are behind a Cloudflare challenge.** `curl` of an article from prod
   and from a home connection: `403`, `server: cloudflare`, `cf-mitigated: challenge`.
   `robots.txt` allows `/` and the feed itself answers `200`. The fetcher already sends a browser
   User-Agent (`DEFAULT_USER_AGENT`, `src/app/ingest/fetcher.py`); only a browser solving the
   challenge would pass, which is bypassing bot protection: excluded.
2. **The admission call does not see the RSS description.** Prod runs with
   `AINEWS_DAILY_ENRICHMENT_ENABLED=true`, so `JevRelevanceScorer.state` sends
   `jev_state(article, with_summary=False)` (`src/app/core/jev.py`) = `Title: ...\nContent: ...`.
   For OpenAI the content is empty, so Jev decides on the **title alone**; the one-line
   description is stored in the candidate payload but never sent. The exclusion of the summary
   comes from re-enrichment (`reenrich_pilot.source_state`: "Exclude both old and generated
   summaries from provider evidence"), where `articles.summary` may be a generated text. At
   ingestion the summary is the publisher's own feed description, not a generated one.

Even an accepted OpenAI item does not reach the digest: Uber (accepted 2026-10-22, article 99564)
was held from the 2026-10-22 digest with `insufficient_source_or_date_evidence` (grounded
summaries need source text).

## 1. Measurements (prod, 2026-10-23)

Candidates = `admission_decisions` rows whose candidate `published_at` is in the last 30 days,
enabled sources. "No text" = candidate content shorter than 200 characters (the evidence Jev saw).

| Source | Assessed | Accept | Reject | Unresolved | Unresolved % | No text % |
|---|---:|---:|---:|---:|---:|---:|
| openai_news | 29 | 2 | 4 | 23 | 79 | 100 |
| alan-turing-institute ai-rss-feeds-ref (aggregator) | 2 | 1 | 0 | 1 | 50 | 100 |
| alan-turing-institute ai-rss-feed-5 (aggregator) | 3 | 2 | 0 | 1 | 33 | 100 |
| bullrich-dev-tldr-rss-ai-rss | 170 | 105 | 32 | 33 | 19 | 39 |
| olshansk feed-coh | 19 | 17 | 0 | 2 | 11 | 37 |
| towardsdatascience-com-feed | 46 | 35 | 7 | 4 | 9 | 11 |
| olshansk feed-cla | 40 | 25 | 13 | 2 | 5 | 63 |
| simonwillison-net-atom-everything | 52 | 17 | 33 | 2 | 4 | 27 |
| wired | 330 | 35 | 287 | 8 | 2 | 48 |
| all other 60 enabled sources | - | - | - | 0 | 0 | 0-100 |

Full-text extraction failures in `/opt/ai-news/logs/daily-fetch.log` (2026-10-12..23, 12 runs;
successes are not logged):

| Source | `rss.full_text_extract outcome=failed` | Fresh candidates (30 d) |
|---|---:|---:|
| openai_news | 260 (20 per run = every extracted item) | 29 |
| becominghuman | 120 | 0 |
| archieai_medium | 120 | 0 |
| ai_roadmap_institute_medium | 72 | 0 |
| towardsdatascience-com-feed | 20 | 46 |
| machine_learning_mastery | 20 | 0 (12 articles stored, all without text) |
| bullrich-dev-tldr-rss-ai-rss | 14 | 170 |
| alan-turing-institute ai-rss-feed-5 | 9 | 3 |

Sources that behave like OpenAI (no text, high unresolved): only `openai_news` at a volume that
matters. The Medium-hosted feeds fail extraction every run with the same `RuntimeError` (status
not checked) but brought no fresh candidates in the window. TLDR is the second-largest beneficiary
of a fix (33 unresolved, its descriptions are real summaries).

Also seen, out of scope: 844 OpenAI candidates are still `pending` from 2026-10-10..12 (archive
items; handled by `docs/prompt-stale-pending-replay-2026-10-23.md`); and all candidates of the
HTML test-tool blogs (testlodge, artillery, tracetest, ...) were rejected in the window.

SQL (run as `ssh ai-news 'docker exec -i ai-news-db psql -U ainews -d ainews' < file.sql`):

```sql
-- per-source outcomes and no-text share
with c as (
  select s.source_key, s.enabled, a.provider_status, a.decision,
         nullif(a.payload::jsonb->'candidate'->>'published_at','')::timestamptz as pub,
         coalesce(length(a.payload::jsonb->'candidate'->>'content'),0) as clen
  from admission_decisions a join sources s on s.id=a.source_id)
select source_key,
  count(*) filter (where provider_status='ok') assessed,
  count(*) filter (where decision='accept') acc,
  count(*) filter (where decision='reject') rej,
  count(*) filter (where decision='unresolved') unres,
  round(100.0*count(*) filter (where decision='unresolved')
        /nullif(count(*) filter (where provider_status='ok'),0)) unres_pct,
  round(100.0*count(*) filter (where provider_status='ok' and clen<200)
        /nullif(count(*) filter (where provider_status='ok'),0)) notext_pct
from c where enabled and pub >= now() - interval '30 days'
group by 1 order by unres_pct desc nulls last, assessed desc;
```

```sh
grep -o "event=rss.full_text_extract outcome=[a-z_]* source_key=[^ ]*" \
  /opt/ai-news/logs/daily-fetch.log | sort | uniq -c | sort -rn
curl -sI https://openai.com/index/decisions-api | grep -i "^server\|cf-mitigated"
```

Matching for section 2: for each unresolved item a title/summary/content `ILIKE` pattern (company
or product name) over `articles` of other sources discovered from one day before to four days
after the OpenAI date; hits were checked by hand.

## 2. Secondary coverage of the 23 unresolved OpenAI items

**6 of 23** reached the site through another source within a day; 1 more only as related coverage.

| OpenAI item (date) | Other source (date) |
|---|---|
| Bringing GPT-Rosalind to academic research labs (10-15) | The Decoder (10-16) |
| Advancing coding in low-resource programming languages (10-19) | The Decoder (10-20) |
| OpenAI acquires Orchestra Bio (10-20) | TechCrunch (10-20), The Decoder (10-21) |
| OpenAI models are coming to Google Cloud (10-21) | The Decoder, Ars Technica (10-21) |
| Using thousands of AI agents ... biological data (10-21) | The Decoder (10-22) |
| Build more responsive apps with the Decisions API (10-22) | TechCrunch (10-22) |
| Patch the Planet (10-21) | related only: TechCrunch "PHP Armageddon" (10-21) |

Not covered (16): 11 customer stories (Higgsfield, Amp, Third Moment, Block, Benefit Street, Itau,
Stack Overflow for Agents, Terminal X, franchisee, Cloudflare, AT&T), 3 policy posts (EU agentic,
democratic governance / cyber defenders, broad access), 2 engineering posts (ChatGPT ad stack, FDE).
The accepted Uber story was also covered by TechCrunch (10-22).

So the actual news (acquisitions, partnerships, products, research) already arrives via
TechCrunch / The Decoder / Ars; what is lost is mostly OpenAI's customer and policy posts.

## 3. Options

| Option | What readers see | Cost | Risk | Size |
|---|---|---|---|---|
| a) Trusted first-party sources admitted on title + description, `evidence: feed_only` | all OpenAI posts on the site, ads expansions and hiring posts too; digest still holds them (no source text) unless the digest changes as well | $0 Jev saved per item | removes the quality gate for a whole source; new `sources.yaml` field and a second admission path | medium: schema field, pipeline branch, digest branch, tests |
| b) Another legitimate OpenAI feed with text | `community.openai.com/c/announcements/6.rss` (Discourse, full post text, 25 items): API/product announcements only (Decisions API, Google Cloud, GPT-Live); links to the forum. `developers.openai.com/rss.xml`: docs and guides, not news. `status.openai.com`: incidents. Help center: 403 | one Jev call per new item, as any source | duplicates stories already covered by TechCrunch / Decoder; does not cover the lost customer and policy posts | small: one `sources.yaml` entry |
| c) Rely on secondary coverage (no change) | main OpenAI news via other sources within a day (6/23 here); customer and policy posts missing | $0 | OpenAI's own posts stay missing; TLDR and aggregators keep losing ~19% to "unresolved" | none |
| **d) Send the feed description to admission when the item has no text** | Jev decides on title + publisher description instead of title alone: fewer "unresolved", more OpenAI / TLDR items on the site list, the rest correctly rejected; digest unchanged (still needs source text) | no extra calls: one Jev call per new candidate as now, ~50 input tokens more (one call ~ $0.0001) | a feed description is marketing copy; Jev may accept a customer story that adds little. Cached decisions of already-seen items stay (no re-screen of the 2015+ archive) | small: `JevRelevanceScorer.state`, doc rule, pinned-text test |

## Recommendation

Do **d** (fixes the cause for every feed-only source, no new paid calls, keeps the Jev gate) and
keep **c** for the digest: feed-only items stay out of the digest, because its grounded summaries
need source text and the real OpenAI news already arrives via TechCrunch / The Decoder. Skip **a**
(removes the gate) and **b** (adds duplicates, not the missing posts).

Implementer prompt: `docs/prompt-feed-description-admission-2026-10-23.md`.

Decided by the agent (reported, not asked):

- Cache keys stay as they are: `bounded_evidence` already hashes title + summary + content, and
  the 2015+ archive is not re-screened; only new candidates (and fresh pending replays) get the
  description. Decided 2026-10-23 (agent): re-screening the archive would add ~1.4k calls and
  put old posts on the site.
- The digest is not changed; the admission provenance hash stays title + content, so daily
  enrichment keeps reusing the admission answer.

## Owner questions

1. Пускать на сайт (в ленту, не в дайджест) посты OpenAI и других RSS-источников без текста
   статьи, если Jev одобрит их по заголовку и однострочному описанию из RSS? Платных вызовов не
   прибавится. Рекомендую: да.
2. Оставить дайджест как есть: посты без текста статьи в него не попадают, главные новости OpenAI
   приходят через TechCrunch / The Decoder? Рекомендую: да.
