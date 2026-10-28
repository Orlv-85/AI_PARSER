# Report: user agent options, decision note (2026-10-28)

Prompt: `docs/work/prompt-ua-options-2026-10-28.md`. Research by a background agent (Sonnet); the
agent could not write files, so the coordinator saved its note and added the measurement below.
No code changed.

## Question

The fetcher and the archive send `DEFAULT_USER_AGENT`, a Chrome-on-Mac string. Switch to an honest
bot user agent (e.g. `ai-news-collector/<version> (+https://<site>/about-bot)`)?

## Where user agents are set

- `src/app/ingest/fetcher.py:8` `DEFAULT_USER_AGENT` (Chrome); RSS and HTML fetch via
  `Fetcher.user_agent`; `Fetcher` is built in `core/ingestion/pipeline/fetch.py`,
  `core/ingestion/pipeline/html_links.py`, `core/sources/validation.py`.
- Archive capture, full-text/evidence download and the robots.txt fetch use `make_http_client`
  (`storage/article_evidence_cache.py`), called from `core/archive/capture.py` and
  `core/daily/enrichment.py`; the source review probe (`core/sources/review.py`) too.
- `scripts/sources_onboarding_helper.py` sends plain `Mozilla/5.0`.

## Facts

- Fetch failures on prod, nights 2026-10-21..27: `www.intel.com` 403 every night,
  `data-flair.training` 403, `replit.com` 429 (`blog.replit.com` redirects there),
  `www.hackerearth.com` 403 on 10-21..24, `community.intel.com` and `www.anaconda.com` 403 at times.
- Archive: `failed: {http_403: N}` 22 on 10-24 and 10-25, 2 on 10-27 (DB: 22 of them are
  openai.com documents).
- robots.txt is read only by the archive/evidence downloader, matched against the Chrome string; a
  403/5xx robots answer means "disallow all". RSS/HTML fetch never reads robots.txt; the
  `respect_robots` flags in config are not used by any code.

## Measurement (coordinator, 2026-10-28, one request per user agent and URL)

| URL | Chrome UA | Bot UA |
|---|---|---|
| data-flair.training ML feed | 403 | 403 |
| blog.replit.com | 301 | 301 |
| www.hackerearth.com/blog | 200 | 200 |
| openai.com/news/ | 403 | 403 |
| www.intel.com newsroom | **403** | **200** |

Same results from the Mac and from the prod server, so these are not IP blocks. The honest bot UA
was never worse; intel.com blocks the fake browser string (a Chrome UA without a browser's TLS
fingerprint looks like a disguised bot) and lets the declared bot in.

## Options

| Option | Effect on blocked hosts | Effort | Policy |
|---|---|---|---|
| (a) keep browser UA | no change; intel stays blocked | none | impersonation, which most site terms forbid |
| (b) honest bot UA everywhere | measured: no host got worse, intel unblocked | one shared constant (fetcher, probe, evidence client) plus tests, about 2-3 files | declared crawler; robots rules apply to our real name |
| (c) (b) plus a per-source override in `sources.yaml` | as (b); overrides only where a host is proven to need it | schema field, plumbing, tests, about 4 files | narrow, auditable exceptions |
| (d) bot UA for the archive only | archive only | one line plus a test | ingestion still impersonates |

## Recommendation

(b) now: one honest bot user agent for fetch, archive and probes, with a URL that explains the bot
(the site's home page until an `/about-bot` page exists). Add the per-source override (c) only if a
host is shown to need it. Leave `respect_robots` as is (record it in the backlog).

## Question for the owner

Switch to an honest bot user agent everywhere (option b)? Recommended: yes.
