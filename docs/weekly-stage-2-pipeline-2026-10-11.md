# Weekly report 2026-10-11: stage 2 pipeline handoff

Stage 2 prepares calculation; it is not the generated or published report. No live
provider calls, production writes, release, merge or scheduler changes were made.
Incremental provider cost: **$0**. V2 remains disabled by default.

## Code and input

Base: `origin/master` `f83594a24fa74ce78da8dc8e64eaab8694bd46bc` (production
v0.1.86). Branch: `feat/weekly-stage2-manifest-v4`. Working checkout:
`/private/tmp/ai-parser-weekly-stage2-20261012`. The shared archive checkout and
its index were preserved. The implementation commit and PR are recorded in the
follow-up version record below after committing this handoff.

The public stage 1 handoff, four-stage plan and associated prompts are included
in this PR. Existing untracked historical-preview scripts/tests and unrelated
prompts are not included. Private corpus, SQLite files, responses and journals
remain outside Git.

The five input byte hashes are in
[the public SHA256 map](weekly-stage-1-hashes-2026-10-11.json), identical to
[stage 1](weekly-stage-1-input-2026-10-11.md). Private immutable input root:
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage1-20261011`.
The runner verifies every hash before parsing the input, including the receipt.
Only `selection-manifest-v4.json` is accepted. Byte hashes, spaced source
fingerprints and compact weekly keys are computed separately.

## Changes and verified scope

- `WeeklyStore.freeze_input()` selects current Article/date/admission evidence.
  Historical observations remain in their ledger and are referenced by ID;
  stale timestamps/text, orphan Articles and unverified alias source identities
  cannot replace current input. Confirmed Articles need no observation to qualify.
  Unknown/conflicting/normalized dates are kept in explicit quality/accounting pools.
- Calendar evidence retains its literal date and possible UTC interval. A week-safe
  date does not become a timestamp or a support day. Timestamp-based event matching
  skips these records; uncertain event groups remain facts with incomplete matching.
- The calculator retains observed event groups, publisher counts, unresolved
  denominators and source evidence when no comparable cohort exists. Unavailable
  normalized metrics are null. Existing states, quality gates and UI are preserved.
- Mandatory editorial admission uses the existing JEV admission question on the
  selected source text. It is independent of daily categories and generated summaries.
  Its cache survives taxonomy changes. Provider failures remain unresolved; a topic
  relevance result contradicting accepted admission cannot silently drop an Article.
- `scripts/weekly_frozen_report.py` prepares and resumes an isolated frozen revision.
  It reuses the existing payment journal with request-specific conservative reserves.
  `publish` imports a reviewed payload via `WeeklyStore.publish()` without models.

All **5,993 Articles** are accounted for. All **932 week-assigned inputs** remain
in the frozen scope: W0 **266**, W1 **158**, H2/H3/H4 **95/199/214**. The 2,350
unassigned dates, 26 ambiguous boundaries and 2,685 outside-scope Articles remain
in explicit accounting. The corrected June/July Articles 95681/95682 stay outside.
The 54 stale conflict-date observations and 85 runtime deleted rejects do not return.

The selected source tuple uses verified page title/body, with generated summaries
excluded. **110** of stage 1's 114 accepted candidates retain compatible admission;
four ledger-based references do not prove this selected tuple and remain unresolved.
Thus **822** dated inputs require fresh compatible admission, rather than 818.
All **123** week-safe calendar inputs are retained; initially **10** have compatible
admission. The other calendar inputs can qualify after fresh admission, without
inventing their UTC support day.

Full-key verification found **two positive compatible assignment decisions** on
the selected source tuple. These are newly verified reuse, not automatic imports
of the 154 conditional keys from stage 1. Only successful assignment payloads are
imported after admission and complete text/task/model/prompt/taxonomy/caps checks.
Pilot progress, eligibility, dates, event IDs and narratives are not imported.

## Validation

- Final repo-wide `make lint PYTHON=./venv1/bin/python`: passed, including ruff,
  mypy and pylint. CLI runner also passed scoped ruff and help checks.
- Final repo-wide `./venv1/bin/pytest`: **867 passed, zero skips**, with an isolated
  UTF-8 PostgreSQL 14 cluster on a private Unix socket and test-local SQLite.
  The cluster is stopped after verification. Initial environment failures were
  corrected: sandbox socket access and an absolute shared SQLite override.
- Synthetic regressions cover current/stale/conflict/deleted inputs, complete reads,
  unknown/normalized/calendar dates, no synthetic day support or timestamp matching,
  exact-key reuse mismatches, admission/provider failure, cumulative money limits,
  per-run resumption, unknown billing, and provider-free payload publication.
- Private aggregate verification additionally hydrates the snapshot into isolated
  SQLite and exercises live freeze. It selects 932 current Articles, accounts for
  all 5,993, and excludes the specified stale/conflict/normalized and June/July groups.
  Counterfactual synthetic assignments on the private scope verify that the empty
  cohort preserves facts and all 822 unresolved denominator entries. This is a
  regression fixture, not semantic classification of the real corpus.

Private verification receipt:
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage2-private-verification.json`.
The private verification script is retained in this worktree's ignored `tmp/`.
Real assignment precision and explanations have not been certified in stage 2.

## Stage 3 command, budget and resume

Use the above checkout, with `PYTHONPATH=src` so the shared `venv1` imports this
checkout's code. The already prepared **current** private run root is:
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage3-20261011-manifest-v4-r2`.
The earlier zero-call preparation without `-r2` is superseded and retained for audit.

Frozen input/cache/budget identity:
`af8c25822c3b2e461bfb5e56995cd3831b5a1f5c27c1f407d68f95902fbea6ff`.
`frozen.json` includes input hashes, selected packet, compatible imports, admission
configuration, code hashes, prices and immutable cumulative monetary caps.
Code or preparation changes require a separate revision; do not overwrite this input.

Reproducible preparation, with **zero model calls**:

```sh
rtk proxy env PYTHONPATH=src ./venv1/bin/python scripts/weekly_frozen_report.py prepare \
  --input-root /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage1-20261011 \
  --root /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage3-20261011-manifest-v4-r2 \
  --hashes docs/weekly-stage-1-hashes-2026-10-11.json \
  --total-budget-usd 10 --jev-budget-usd 7 --deepseek-budget-usd 3
```

The paid calculation command is for **stage 3 only**; it was not run in stage 2:

```sh
rtk proxy env PYTHONPATH=src ./venv1/bin/python scripts/weekly_frozen_report.py run \
  --root /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage3-20261011-manifest-v4-r2 \
  --env-file /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.env \
  --approve-paid
```

Fresh admission for the 822 unresolved dated inputs is explicitly part of `run`,
using JEV on the verified selected source text; accepted source proofs are reused.
Weekly classification and bounded event checks then use JEV; ambiguity resolution
and up to eight evidence-bearing other-signal explanations use DeepSeek with JEV
claim-support checks. Python alone computes metrics and states.

Hard cumulative caps: **$10 total / $7 JEV / $3 DeepSeek**, including attempts from
all restarts. They do not inherit the old $2 pilot. Existing peak pricing constants
are frozen, with no off-peak/cache-discount assumption; stage 3 must verify official
rates before dispatch. At the frozen rates, reserving one request for every fresh
admission and uncached assignment is at most about $4.71 before event/ambiguity work.
This is a conservative reservation estimate, not an invoice or a guarantee that all
possible event comparisons fit. If the cap is reached, stop and present the concrete
remaining scope/cost; do not bypass safeguards or reset the journal.

Run limits remain 1,000 JEV decisions, 100 ambiguity calls, 16 narrative calls and
900 seconds per invocation. Repeat the **same run command and root** for ordinary
budget/lease resumption. `weekly.sqlite` stores job/cache/taxonomy/snapshot progress;
`journal.sqlite3` durably stores each dispatched request, response, usage and cost.
Unknown billing, missing usage or failed requests stop further paid dispatch and
require review; repeating the command does not repay them. Failed/unresolved source
admissions remain in the denominator and cannot become semantic rejections.

Outputs: `candidate.json`, `usage.json`, `weekly.sqlite`, `journal.sqlite3` and
`frozen.json`, all private. Completion returns a snapshot ID and cumulative usage.
Repeating a completed run recovers the existing payload with zero provider replay.

## Limits and stage 4 publication

No comparable publisher cohort or complete New history is proved. Up/Down/New
cannot be confirmed by changing thresholds. Expect `insufficient_evidence`, existing
quality reasons, observed topic facts and sources, null unavailable normalized
metrics, and explicit calendar/event/admission limitations. No section has a quota.

Stage 4 can publish the reviewed `candidate.json` without calling models. Migrate
the target DB using the normal deployment workflow first, verify the payload hash,
backup the target, and provide its database URL through an environment variable
named `WEEKLY_TARGET_DATABASE_URL` (never print its value):

```sh
rtk proxy env PYTHONPATH=src ./venv1/bin/python scripts/weekly_frozen_report.py publish \
  --root /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage3-20261011-manifest-v4-r2 \
  --candidate-sha256 <reviewed-stage-3-file-hash> \
  --database-url-env WEEKLY_TARGET_DATABASE_URL --approve-publication
```

This validates payload provenance/full scope, leases only the matching job, creates
an immutable new target revision and uses the normal atomic publication pointer.
Existing ready-report protection and legacy storage remain intact. Re-import is
idempotent. Production visibility/feature flag, deployment and API/UI verification
belong to stage 4; no flag is enabled by this command or stage 2.

Next-session prompt:
[stage 3 from this frozen revision](prompt-weekly-stage-3-from-frozen-v4-2026-10-12.md).
Every future session/handoff prompt must first be saved in a descriptive
`docs/prompt-<task>-<YYYY-MM-DD>.md`, preserving prior prompts, and linked to the user.
