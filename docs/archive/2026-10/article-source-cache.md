# Unpaid article source evidence cache

`scripts/reenrich_articles.py` downloads only the frozen existing source URLs
and follows ordinary article redirects. It does not crawl source archives,
invoke JEV/DeepSeek/Codex, generate summaries/categories, or change production
articles, admission decisions, published reports, retention or weekly settings.
Only aggregate counters and hashes are printed. Article HTML/text stay private.

## Preparation

Use a fresh read-only database export including every `EXPORT_TABLES` table,
plus the original unresolved review. The run directory must be private and,
when inside this repository, under ignored `tmp/` or `data/`.

```sh
rtk proxy ./venv1/bin/python scripts/reenrich_articles.py prepare \
  --snapshot /private/current-snapshot.json \
  --review /private/review-unresolved.json \
  --run-dir /private/reenrich-run
```

Preparation freezes current IDs, original URLs, row/evidence hashes and
dependencies. Missing IDs and changed canonical identities are recorded instead
of fetching a different article. Current source evidence remains separate from
the original review evidence. An existing run refuses a different snapshot or
review. Ordinary application imports read local settings; use a valid local
configuration and an explicit isolated SQLite URL for local tooling/tests.

## Download and resume

```sh
rtk proxy ./venv1/bin/python scripts/reenrich_articles.py fetch \
  --run-dir /private/reenrich-run --concurrency 8 --host-interval 1
rtk proxy ./venv1/bin/python scripts/reenrich_articles.py status \
  --run-dir /private/reenrich-run
rtk proxy ./venv1/bin/python scripts/reenrich_articles.py verify \
  --run-dir /private/reenrich-run
```

Concurrency is bounded and requests to one host are serialized and paced.
`robots.txt` is loaded and cached once per origin; deny/unavailable responses
leave the article unresolved. Redirects to home/login/directory pages stop
without fetching that destination. No automatic request retry is performed.
429 stops further requests to the affected host; repeated 503 responses also
pause it. Ten consecutive connection failures across distinct hosts stop new
dispatches and leave undispatched URLs pending.

Each page is addressed by SHA-256 of its original URL without the fragment.
Shared URLs can reuse their saved page for date-only or model stages. The cache
stores raw decoded response bytes (`body.bin`), normalized UTF-8 HTML
(`page.html`), extracted text (`text.txt`), HTTP/final-URL/redirect/fetch metadata
(`response.json`), date and quality evidence (`evidence.json`), and durable
attempt state (`attempt.json`). Files use mode 0600, directories 0700. The
run lock prevents two download processes from operating on the same cache.
After download, `verify` checks every completed response, HTML/text/evidence
hash, content-file permissions, source/redirect URL policy and frozen identities.
It prints aggregate verification counts and hashes only. Unfinished or corrupt
entries prevent a successful verification receipt.

An attempt is journaled before network dispatch. Completed, failed, blocked
and interrupted attempts are not automatically fetched again on resume.
If response bytes and metadata were already saved before interruption, resume
checks their hash and completes extraction offline. A `started` attempt with
no saved response has an uncertain fetch outcome and requires operator review.
Future deliberate retries or extraction changes must preserve prior artifacts
and their provenance; they are not implicit in the resume command.

## Evidence and limitations

Date metadata is extracted before scripts are removed. Supported evidence
includes Article/NewsArticle/BlogPosting JSON-LD, publication/modification meta
tags and microdata. Explicit visible time labels are retained for later literal
parsing. Modified dates remain separate. Date-only values retain day precision;
timestamps without a timezone do not acquire one. Conflicting or missing
publication evidence remains explicit. Event, footer, navigation, URL and HTTP
Last-Modified dates are not substituted for publication dates.

`extracted` is a deterministic quality flag, not an AI/editorial admission
decision or a guarantee that every word belongs to the article. Short bodies,
paywall markers, blocked/error titles, redirects, non-HTML, malformed pages and
oversized responses are unresolved. All original database rows remain untouched.
JEV must later assess cached source evidence under the agreed taxonomy and
existing conservative cleanup policy. Generated summaries are a separate asset.

## Offline dates for other articles

```sh
rtk proxy ./venv1/bin/python scripts/reenrich_articles.py audit-dates \
  --run-dir /private/reenrich-run \
  --legacy-snapshot /private/original-pre-cleanup-snapshot.json
```

This checks non-review articles against original admission candidate payloads
and observations explicitly marked as source publication evidence. Cleanup
copies, article-row timestamps, updated-only candidate dates and unverified
observations do not constitute publication proof. The private audit records
candidate origins and conflicts; the command outputs aggregates only.
The original weekly observation writer already distinguished RSS publication
from updated-only timestamps when the table was introduced (`f9c058a`).
Legacy normalized timestamps do not retain the original literal date precision;
that limitation is explicit in the audit. This command does not fetch additional
URLs or apply dates. Additional date-only fetches are a later stage.
