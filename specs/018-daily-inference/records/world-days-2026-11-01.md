# World stream, first night: 2026-11-01 (FR-018)

Night of 2026-11-02 on v0.1.155, first run with `AINEWS_WORLD_COLLECT_ENABLED=true`. Sources:
`/opt/ai-news/logs/daily-world.log`, `ai-news world report --date 2026-11-01`, `systemctl show`
(read-only). This night collected D-1 (2026-11-01) and the one-time D-2 catch-up (2026-10-31), so
its counts and cost are about twice a normal night.

## Nightly jobs (UTC)

| Job | Start | End | Result |
|---|---|---|---|
| fetch | 01:00 | 01:26 | ok; 159 sources, 2694 fetched, 70 new, 10 errors |
| digest + signals | 02:00 | 02:03 | ok; day brief ok ($0.0041), week brief ok ($0.0160) |
| archive | 03:00 | 03:00:55 | ok; coverage 95.3% (703 / 670); downloads 200, `skipped_cap` 723 (see below) |
| world | 04:00 | 04:25:43 | ok (exit 0) |

## World job steps

| Step | End | Time | Numbers |
|---|---|---|---|
| collect 2026-11-01 | 04:05:50 | ~6 min | 192 GDELT files, 187300 rows, 2552 matched, 1934 kept, 1922 new |
| collect 2026-10-31 | 04:11:53 | ~6 min | 192 files, 205050 rows, 3057 matched, 2265 kept, 2255 new |
| screen A (title) | 04:23:51 | ~12 min (limit 2700 s) | 4177 candidates in 3537 requests; 2747 in, 1430 out |
| texts | ~04:25:30 | ~1.5 min | top 100: 74 texts, 26 no text |
| screen B (FR-001) | 04:25:42 | < 1 min | 74 asked, 72 assessed, 2 failed (`JevInputTooLarge`) |

No file missing or skipped, no partial day, nothing pruned. Disk after the night: 8.8 of 25 GB used;
the world journal is 2 MB.

## FR-018 numbers

- Candidates: 4177 over the window 2026-10-31..2026-11-01 (about 2100 per day).
- Share accepted by Jev at step A: 2747 / 4177 = 66%.
- Top 100: text for 74 (no text: paywall 7, robots 8, identity unverified 5, non-HTML 3,
  http_403 2, blocked page 1).
- Step B on 72: changed 36, issue 18, limit 9, added 4, none 5.
- Cost of UTC day 2026-11-02: $0.0718 in 3609 Jev calls (step A $0.0644, step B $0.0074), under the
  $0.10 cap. A normal night (D-1 only) should be about half of step A: ~$0.04.

## Sample (from the report, 20 stories; 8 shown)

| Area | Change | Harm | Outlet | Title |
|---|---|---|---|---|
| Work | issue | 0.73 | kasu.org | Your writing was flagged as AI. What does that actually mean? |
| Health | changed | 0.05 | wach.com | Americans open to AI in health care but want humans calling the shots |
| Law | issue | 0.96 | lactualite.com | OpenAI conteste une decision concernant la tuerie de Tumbler Ridge |
| Speech | issue | 0.47 | boursorama.com | Des chatbots d'IA diffusent de fausses informations sur les elections americaines de mi-mandat |
| Daily life | issue | 0.03 | wiltshiretimes.co.uk | Morrisons ends AI shopping trolley trial after three months |
| Law | changed | 0.36 | localnews8.com | This retired professor was arrested for blocking a delivery robot. She says she'll do it again |
| Security | limit | 0.23 | deccanchronicle.com | OpenAI To Limit Weapons Information For Teens on ChatGPT in Violence-Prevention Push |
| Education | changed | 0.02 | oestadoacre.com | Programa oferece cursos gratuitos sobre IA para professores |

Languages in the sample: English, French, Spanish, Portuguese, Italian, Turkish.

## Findings

1. `JevInputTooLarge` in step B (2 of 74). `world_change_state` bounds the text by characters
   (`CONTENT_LIMIT` 16000), while `reservation` bounds the encoded request by bytes (32000) and
   `encoded` uses `ensure_ascii=True`, so each non-ASCII character costs 6 bytes. Long non-English
   texts fail; the world stream is multilingual, so this will repeat. Fix: bound the state by encoded
   size. Not checked: which two articles failed (the failure is logged without an id).
2. Archive `skipped_cap` 723: not a fault. `ArchiveRepo.due` returns failed documents of any age
   whose retry time has come; 961 documents failed during the 2026-10-31 backfill (first seen from
   2026-07-03) and became due. The cap (`ARCHIVE_MAX_DOWNLOADS` 200) works; all 200 attempts failed
   again (403, paywall, identity, extraction), mostly theverge.com, venturebeat.com, openai.com. A document
   moves to `gave_up` after the last of `ARCHIVE_RETRY_DELAYS` (1, 3, 7 days), so at 200 a night
   this churn lasts one to two weeks. World documents are excluded as designed (W6).
3. The world job ended at 04:25:43, so it held the host lock 26 minutes (the W7 estimate was 25-65
   minutes, worst ~2 h); a 04:00 bulletin job (item 4) still has to wait for it.
