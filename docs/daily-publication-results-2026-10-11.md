# Daily publication repair, 2026-10-11

The completed mass re-enrichment is preserved in commit `4e46089` and regular
release `v0.1.80`. This continuation does not repeat mass cleanup or rewrite
frozen historical digests. Its target is the October 10 daily digest and the
ordinary future scheduled path.

## Implementation

The Ubuntu host uses Europe/Vilnius and classic cron. Its old 01:00 fetch runs
at 22:00 UTC on the previous calendar day in summer; its 02:00 digest runs at
23:00 UTC. UTC `yesterday` therefore selects a day earlier than intended.
`CRON_TZ` in this implementation is not sufficient to change cron's scheduler.

Deployment now removes managed daily cron blocks and installs systemd calendar
timers with explicit UTC: fetch at 01:00 UTC and publication at 02:00 UTC.
For example, both October 12 jobs serve the completed October 11 UTC day;
publication on October 13 serves October 12. Vilnius displays these jobs at
04:00/05:00 in summer and 03:00/04:00 in winter. The host timezone is unchanged.
Both wrappers share the collector lock and select the current released image
from `.last_deploy_image`. Installation does not execute a historical catch-up.
[Systemd calendar timezone semantics](https://github.com/systemd/systemd/blob/main/man/systemd.time.xml).

Ordinary ingestion enables RSS full text, retains publication evidence semantics,
uses the exact validated `pilot-rubric-clarification-3` questions and ten topics,
and saves Comparison metadata and reusable admission proof. Mandatory admission,
reject ledgers and provider-outage pausing remain. Daily JEV calls use the existing
private payment journal implementation with a $1 JEV cap per ingestion UTC date.

The daily worker reads every stored article in the selected UTC day directly,
with no top-200 or relevance cutoff. It reuses grounded English summaries from
re-enrichment and prior daily runs. Otherwise it reuses or acquires bounded source
evidence, checks admission/topic/type, and generates a summary with DeepSeek.
Checks include complete JSON and finish reason, literal supporting quotations,
semantic support/English review, at most 80 words and 400 characters. At most one
narrow repair is allowed; responses and known usage are preserved for resume.
Each report-date journal caps JEV at $1 and DeepSeek at $4; no archive crawl or
weekly generation is enabled.

The previous batch generator collapsed JSON/schema, URL coverage, output
truncation and summary-length failures into one `invalid summaries` message and
retried the same broad request. Historical raw responses were not retained, so
the exact failing constraint of the old October 10 execution cannot be reconstructed
from that message. It must not be conflated with earlier proxy errors.
The scheduled path now uses per-article grounded output, a 4096-token JSON budget,
and distinct private failure reasons while retaining the substantive checks.
[DeepSeek JSON output/truncation guidance](https://api-docs.deepseek.com/guides/json_mode/).

The excerpt fallback is removed from the scheduled path, even if the old fallback
environment flag remains. A provider failure leaves the previous digest unchanged.
Source/date/classification holds remain explicit in the private report and never
become raw-excerpt digest items. A supported subset is labelled
`published_with_holds`, with complete scope enumeration but incomplete enrichment.
Per-article commits and a durable journal allow resume without resummarizing
successful rows. Replacement of a previous target digest is atomic and follows
a private JSON backup. Other historical report dates are untouched.

## Validation and production receipt

Implementation validation: full `make lint PYTHON=./venv1/bin/python` passed;
full pytest with file-backed isolated SQLite and isolated local PostgreSQL 18:
842 passed, no skipped tests. PostgreSQL migration coverage now includes
`a42b750d0c44` when rehearsing the weekly store's existing contract.
Tests include >200 daily articles, ordinary admission journal reuse, preserved
historical reports, provider outage, truncation, unsupported summaries, explicit
evidence holds, repeat publication with no paid requests, and UTC timer units.

The first PR CI run passed assertions and lint but failed the 90% coverage gate:
its PostgreSQL tests were skipped and coverage rounded to 89%. Both branch and
release workflows now provision an isolated PostgreSQL 18 service and pass its
test-only connection to the Docker test container; the threshold remains 90%.
A Docker image built from the committed files, excluding unrelated untracked
user files, passed **838 tests, zero skipped**, and the coverage gate at **91%**.
The local worktree's 842 count also includes four unrelated untracked tests.

PR [#17](https://github.com/Orlv-85/AI_PARSER/pull/17) was merged as
`f4744abbf1fe0af12aea7d9e5c4774d4e41878ec`; regular release `v0.1.81`
successfully built and deployed. Production uses
`ghcr.io/orlv-85/ai-parser:v0.1.81`, preserving migration `a42b750d0c44`.

The first dated October 10 run enumerated 50 articles and stopped safely after
one successful enrichment and seven evidence/classification holds. A complete
DeepSeek reviewer response (`finish_reason=stop`) contained `facts` rather than
the required `supported` and `english` booleans. It did not publish a digest.
The first run's 4 JEV / 6 DeepSeek calls cost $0.002592 on conservative usage rates.

The bounded follow-up keeps the failed billed response and attempts one distinct
review-schema recovery, without regenerating its summary. A private recovery
probe reused the original review and made one new reviewer call; its correct
boolean verdict was unsupported. Such a definitive semantic refusal is now an
explicit `summary_not_supported` hold, while provider outages, repeated invalid
review schemas and malformed/truncated summary generation still preserve the
previous report. All literal quote, length, English and semantic checks remain.
Cumulative daily usage after that probe: $0.002750, with no unknown billing.

Private full backup: `/opt/ai-news/backups/daily-publication-20261011/full-before-release.dump`.
SHA-256: `8efe015e0d60e749f4339045d5d479c72b613141c5e8c7800e281220d740579e`.
The historical report snapshot contains 4,925 items, with hash
`d5af571aead64595ae915d560f0462605246ae806039e5509257c34a8c3fe421`.
Daily source cache, responses/payment journal and resumable receipts are under
`/opt/ai-news/data/daily-enrichment/`; SSH/operation receipts are private under
the backup directory and local ignored `tmp/`.

The final publication receipt will be appended after the follow-up release and
API/page verification. A manual dated run is not evidence that the next regular
scheduled timer has fired.
