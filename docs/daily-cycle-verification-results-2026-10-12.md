# Daily cycle verification and hold recovery, 2026-10-12

Production was verified at **06:20:05 UTC on October 12**. The actual automatic
cycle ran, but **successful automatic publication is not yet confirmed**.
The first scheduled digest failed; the later repair was a manual dated resume.
The next scheduled cycle is October 13 at 01:00/02:00 UTC, serving October 12.
No hours-long wait or timer alteration was performed.

## Actual scheduled executions

- Fetch started October 12 at 01:00:00 UTC, exited at 01:19:26 with status 0.
  Its receipt records 2,191 fetched, 137 new, 755 duplicates, five errors,
  25 not-modified sources, 524 skipped known HTML links and eight early stops.
  It nevertheless paused screening on one local oversized request, so exit 0
  does not imply complete ingestion.
- Digest started at 02:00:00 UTC and exited at 02:00:14 with status 1.
  Scope was 11 October 11 articles. It failed at `invalid_daily_assessment`
  before any daily-provider dispatch, preserving the previously stored state.
- Effective systemd timers remain 01:00 UTC fetch and 02:00 UTC digest.
  The wrappers choose `.last_deploy_image` and share the collector flock.
  Managed daily/weekly cron commands are absent; host timezone remains Vilnius.
  The failed service result was retained rather than relabelled successful.

## Repairs and installed code

[PR #20](https://github.com/Orlv-85/AI_PARSER/pull/20), implementation
`4e27e6687b2aea555525356e980555d1c21c8de6`, merge
`2989b241281320bb6cc0ec56551546388eb3ef10`, released as `v0.1.84`:

- Ordinary ingestion intentionally drops unresolved classification confidence
  from its saved proof. Daily publication now keeps that partial proof in
  topic/type hold and processes the remaining day without billing admission again.
- Source acquisition now follows up to five public robots redirects, including
  a cached 301, and applies final rules. Denials, loops and private destinations
  remain blocked. Previous attempts and redirect receipts are retained.

[PR #21](https://github.com/Orlv-85/AI_PARSER/pull/21), implementation
`01bc4c2` (full SHA in Git), merge
`56e0f4c497f8d7672e1e87c22e073dcf31d8c7bc`, released as **v0.1.85**:

- One pending source produced a 35,389-byte conservative request against the
  unchanged 32,000-byte limit. This local pre-dispatch failure had been confused
  with a provider outage. Its distinct exception now leaves the source pending
  and unresolved while other screening continues. Daily publication records
  the same situation as `source_input_too_large`.
- Provider/network/schema failures and budget/unknown-billing safeguards keep
  their existing pause behavior. No assessment, date or summary is invented.

Final registry image: `ghcr.io/orlv-85/ai-parser:v0.1.85`.
Image ID: `sha256:4b1216de88d9ec2a9e3c7a5c37d23515cc1be4ee170cb33d1577f6816d0e38e6`.
Migration remains `a42b750d0c44`. Local master and origin/master are at `56e0f4c`.
[Release pipeline 38211676934](https://github.com/Orlv-85/AI_PARSER/actions/runs/38211676934)
passed lint, tests, image build, deploy and registry cleanup.

The saved oversized candidate was revalidated on the released image with all
network dispatch forbidden: input held, provider not failed, candidate still
pending, journal unchanged. All 574 recorded ingestion responses had valid
relevance/admission fields and known usage. The stale pause was cleared only
after locking and checking that its timestamp still matched that diagnosed
local failure, with a private CollectionStatus backup. Collection is unpaused;
the public warning disappeared. This is a targeted state correction, not proof
of a later successful scheduled cycle.

## Publication and holds

| UTC report date | Scope | Published | Holds | Result |
| --- | ---: | ---: | ---: | --- |
| October 10 | 48 | 7 | 41 | Existing summaries reused; two erroneous dates corrected |
| October 11 | 11 | 1 | 10 | Manual resume after scheduled failure |

October 10 initially had 43 holds, including 36 source/date holds. Cached
diagnosis found five paywalls, six robots blocks, seven short extractions and
22 unverified identities; signals overlap. Source dates were unknown in 25,
confirmed in five and absent in six. No conflicting structured dates were found.
The direct robots blocks were two Cognition redirects, two X denials and two
Towards Data Science responses with HTTP 202. Paywall markers belonged to the
articles themselves. Many identity holds are undated landing/list/profile pages;
four AGI Inc. pages also expose older visible dates rather than October 10.

Only the two Cognition source requests were retried after the redirect fix.
Both yielded usable extracted evidence, proving dates **July 1 and June 29**.
Their publication fields were repaired through the existing transactional,
drift-checked apply mechanism, with a private manifest and targeted rollback.
They therefore leave the October 10 scope; they were not deleted or forced into
that digest. No other historical digest was generated for their corrected dates.

October 10 was republished atomically after `digest-before-20261012T061526675905.json`
was saved. Network/provider dispatch was forbidden during this cached-only
operation. All seven successful summaries and compatible paid responses were
reused. **Zero summaries were added to October 10**. Remaining holds:
34 source/date, two admission, three topic/type, two unsupported summary.
The latter seven retain their earlier quality verdicts; no new evidence justified
another model attempt.

The October 11 manual resume completed at 06:12:50 UTC, publishing one supported
English summary in AI Applications. Remaining holds: four source/date, five
topic/type and one unsupported summary after bounded repair/review.
Its admission proofs were reused with zero new JEV calls.

Both public APIs returned 200 with the expected dates/counts. Every published
item matched a row with reusable grounded/reviewed proof. Chrome displayed both
selected dates and their groups/summaries; the October 11 layout was inspected.
The **4,925 other historical digest items** retained the exact original hash:
`d5af571aead64595ae915d560f0462605246ae806039e5509257c34a8c3fe421`.
Auth/admission remain enabled, weekly generation remains off, retention remains
800 days and maintenance thresholds retain their 5/4 GiB defaults.

## Validation and billing receipts

Final repo-wide `make lint PYTHON=./venv1/bin/python` passed (ruff, mypy,
pylint 10/10). Full venv1 pytest passed **854 tests, zero skipped, coverage
91.38%**, using a clean copy of the current files without local `.env`, isolated
file-backed SQLite and dedicated local PostgreSQL 18. Four unrelated untracked
user tests were preserved and included locally; tracked release CI also passed
the unchanged 90% coverage gate. Initial local attempts failed because local
auth settings or a shared absolute SQLite path contaminated test isolation;
those setup failures were resolved before commit/push. No production database
was used for tests. No required final gate was skipped.

| Work | JEV calls | DeepSeek calls | Recorded peak usage-priced USD |
| --- | ---: | ---: | ---: |
| October 10 cumulative publication | 14 | 23 | 0.009935 |
| October 12 scheduled ingestion | 574 | 0 | 0.083015 |
| October 11 manual publication repair | 0 | 8 | 0.003061 |
| Combined daily operations shown here | 588 | 31 | 0.096011 |

Manual continuation added **$0.003061**; Cognition evidence/date repair and the
local input probe added zero model cost. Scheduled ingestion used 1,969,830 JEV
input tokens; the manual resume used 7,611 DeepSeek input / 645 output tokens.
All recorded usage is known; these are the journal's conservative rates, not
provider invoices. Earlier mass re-enrichment spending is outside this table.

Private receipts and backups:

- `/opt/ai-news/backups/daily-cycle-20261012/`: scheduled logs, pre-repair daily
  reports/journal copies, manual resume receipt/log and `final-verification.json`.
- `/opt/ai-news/data/daily-enrichment/hold-recovery-2026-10-12/`: new source cache,
  recovery receipt and `date-correction/` with manifest, rollback, old cache,
  CollectionStatus backup and local-input recovery receipt.
- `/opt/ai-news/data/daily-enrichment/2026-10-10/` and `2026-10-11/`: reports,
  payment journals and atomic digest backup.
- `/opt/ai-news/data/daily-admission/2026-10-12/journal.sqlite3`: scheduled
  ingestion responses and payment reservations.
- Local ignored `tmp/daily-cycle*`, `tmp/scheduled-*`, `tmp/cognition-*`,
  `tmp/local-input-*`: aggregate diagnostics and operational receipts.

Saved next-session task:
`docs/prompt-verify-next-scheduled-daily-cycle-2026-10-12.md`.
This is a local, unfinished handoff preserved in the working copy; it is not
included in the archival PR or available in a clean checkout of that PR.
User preference remains: save each task/handoff prompt before delivering it,
link it, and preserve that rule in future contexts. Existing untracked files
and the user's AGENTS.md change were preserved and excluded from commits.
