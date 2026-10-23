# Report: plan of 016 article archive (2026-10-23)

Planner session, prompt `docs/prompt-archive-plan-2026-10-23.md`. Spec only; gate not run (docs).

## Measured on prod (read-only, 2026-10-23 ~08:40 UTC)

Access: `ssh ai-news`, `docker exec -i ai-news-db psql -U ainews -d ainews` with SQL on stdin;
`df`, `du`, logs and `systemctl list-timers` on the host. No writes, no restarts.

| Fact | 2026-10-18 (backlog) | 2026-10-23 |
| --- | --- | --- |
| Articles | 6595 | 7079 |
| With full text (`length(content) >= 300`) | 2581 (39%) | 3030 (42.8%) |
| Average full text | 9404 chars | 9949 chars |
| All article text (`sum(octet_length(content))`) | 24 MB | 29 MB |
| DB / `articles` table | 122 MB / 40 MB | 146 MB / 40 MB (heap 12 MB, TOAST 24 MB, indexes 4 MB) |
| Free disk | 7.6 of 25 GB | 8.7 GB (63% used) |
| `data/daily-enrichment/source-cache/` | 56 pages | 49 MB, 57 page dirs (20 extracted, 34 unresolved); `body.bin` 24 MB + `page.html` 24 MB + `text.txt` 0.4 MB |
| Oldest article | 2024-08-09 | publication 2017-10-29 (first discovered 2026-07-03) |
| `article_aliases` rows | - | 0 |
| PostgreSQL | - | 18.2 |

```sql
select count(*), count(*) filter (where length(content)>=300),
  round(avg(length(content)) filter (where length(content)>=300)),
  pg_size_pretty(sum(octet_length(content))::bigint) from articles;
select pg_size_pretty(pg_database_size(current_database())), pg_size_pretty(pg_total_relation_size('articles'));
```

Per month of `discovered_at` (total / with full text / %): 2026-10 3106 / 1900 / 61%;
2026-09 995 / 324 / 33%; 2026-08 1520 / 431 / 28%; 2026-07 1458 / 375 / 26%.
Since semantic admission (`discovered_at >= 2026-10-12`): 1185 articles, 1092 with full text (92%):
RSS 896 of 987, HTML 196 of 198; about 92 new articles per day (2026-10-12..22).

```sql
select to_char(discovered_at,'YYYY-MM') mon, count(*), count(*) filter (where length(content)>=300)
from articles group by 1 order by 1 desc;
select s.source_key, s.type, count(*) n, count(*) filter (where length(coalesce(a.content,''))<300) short
from articles a left join sources s on s.id=a.source_id where a.discovered_at >= '2026-10-12'
group by 1,2 having count(*) filter (where length(coalesce(a.content,''))<300) > 0 order by short desc;
```

Sources short of full text since 2026-10-12 (short / total): `openai_news` 38/38,
`raw-...-feed-coh` (Cohere feed) 20/38, `huggingface_blog` 20/42, `lilianweng` 4/23,
`raw-...-feed-cla` 3/13, `fiddler` 2/13, `theagi_company_blog` (HTML) 2/9, `bullrich tldr` 2/94,
`archieai_medium` 1/1, `deepmind_blog` 1/7.
All time, sources with no full text at all: `openai_news` 231, `machine_learning_mastery` 47,
`crewai_releases` 29, an olshansk feed 13, `marek_rosa` 12, `paulhcleverley` 12, `microsoft_ai_blog` 10,
Alan Turing feeds 19, `becominghuman` 5.

Fetch-time extraction failures in `logs/daily-fetch.log` (`rss.full_text_extract outcome=failed`, by
host): openai.com 264, medium.com 192, becominghuman.ai 120, towardsdatascience.com 20 (ParserError),
machinelearningmastery.com 20, cetas.turing.ac.uk 9, perplexity.ai 3, atera.com 3, bloomberg.com 2,
zhihu 1, wsj.com 1. Hugging Face items have no failure line: they fall beyond
`rss_full_text_max_items_per_source` (20), e.g. `huggingface.co/blog/falcon2-11b` discovered
2026-10-23 with empty content.

Older than retention (800 days, run by every deploy): 79 articles, 71 with full text.
Jobs: no crontab; timers fetch 01:00 UTC (2026-10-23 run 01:00-01:28), digest 02:00 UTC
(finished 02:10). Production `.env`: `RETENTION_DAYS=800`; `AINEWS_RSS_EXTRACT_FULL_TEXT=1` is set
by `scripts/run_daily_fetch_job.sh`, not `.env`.

## Backlog claims checked against code

- "non-news cleanup deletes article rows": no longer true; the cleanup code was deleted in PR #71
  (2026-10-21). Remaining delete paths: `ArticleRepo.prune_older_than` (deploy and
  `scripts/db_maintenance.sh`) and `entities purge-evidence` (derived evidence only).
- "RSS content when present": `parse_rss` never stores feed content (`content=None`); article text
  comes only from the linked page (`rss_extract_full_text`, first 20 items) or the HTML article page.
- "56 pages cached": 57 today, only for articles daily-publish needed.
- `signal_mentions` no-FK pattern: confirmed (`SignalMention` docstring, plan Decision 4 of 006).
- A0 backups: done (`scripts/db_offsite_upload.sh`, `scripts/db_offsite_restore_test.sh`).

## Decisions (all decided 2026-10-23 by the agent unless a source is named)

1. Storage: two tables in the application PostgreSQL, no files yet. Why: off-site backups already
   cover the DB; size is small (29 MB today, ~0.35 GB/year). Cold files deferred to 2 GB.
2. Identity: canonical URL hash, one document per hash; no cross-source dedup. Source: ingestion
   decision of 2026-10-20 in `pipeline.md` (canonical hash is the only identity; grouping at read time).
3. Versions: append-only, new version only when the text hash differs.
4. No FK to `articles`/`sources`. Source: backlog A1 and the `signal_mentions` pattern (006).
5. Prune archives before delete in the same transaction. Why: 79 rows are past the cutoff today; a
   seed run alone could come after the next deploy's prune.
6. Raw HTML not in DB; file cache kept 14 days. Why: 0.86 MB per page dir measured; backlog proposed
   30 days, 14 bounds disk at ~0.25 GB and still allows re-extraction after a fix.
7. Minimum text 300 chars, same bar as `inspect_page` and daily `source_row`.
8. Capture as its own systemd timer at 03:00 UTC under the shared lock, not a step in fetch/digest.
   Why: failure isolation (backlog A3 requirement) and reuse of pages daily-publish downloaded.
   The backlog's proposal "step after fetch" was rejected for this reason.
9. Reuse `SourcePageDownloader`/`PageCache` (backlog A2 proposal) with an archive-owned cache root;
   the daily-publish cache is read only.
10. Retry 1, 3, 7 days then give up; 404/410/robots/non-HTML/redirect-to-non-article give up at once.
11. Caps: 200 downloads per run, 20 per host, concurrency 4 (same as daily `acquire`).
12. User agent: reuse `DEFAULT_USER_AGENT` (a browser string), the identity the fetcher already
    uses on the same sites. Flagged for A7 (see risks).
13. Seed with `archive capture --all --no-download`; downloads of old articles are A2.
14. No author/language/license columns now (nothing extracts them); A5 adds nullable columns.
15. No archive text on any page or API, admin included; admin counts optional (T012).

## Owner questions (product or money)

1. Public `GET /api/news/links?include_content=true` returns up to 12000 chars of stored article
   text to anonymous callers (`web/routes/news.py`, path is in the public list of `web/app.py`).
   This republishes third-party full text, against the archive principle "never republish".
   Close `include_content` for anonymous callers (keep it for logged-in users and MCP)? Recommend: yes.
   Not part of 016; would be its own small PR.
2. No paid calls in this spec (capture is deterministic, no model). No money question.

## Risks

- `DEFAULT_USER_AGENT` imitates a browser; robots.txt rules for named bots do not apply to it.
  A7 should decide whether to switch to an honest bot UA (may raise 403s).
- openai.com answers 403: ~38 articles per 11 days will end `gave_up` (separate investigation
  prompt `docs/prompt-openai-source-investigation-2026-10-23.md`).
- Text from `articles.content` has no recorded extractor version (`ARTICLE_CONTENT_VERSION` marks it).
- Coverage target (90%) depends on hosts like medium.com that block extraction; measured 92% from
  fetch alone, so the target is met even if downloads add little.
- The seed is a production write: needs the owner's yes after Phase 2 deploys.
- Disk: 8.7 GB free; archive and raw cache add < 1 GB per year at current volume.
