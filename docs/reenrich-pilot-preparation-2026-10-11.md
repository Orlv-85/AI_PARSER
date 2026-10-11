# Cache-only pilot prepared, payment checkpoint

Historical preparation receipt. The user subsequently confirmed the proposed
$1.50 / $0.25 / $1.25 caps and the pilot ran once, stopping at 21/80 on an
incomplete DeepSeek response. The current state is in the
[paid checkpoint](reenrich-pilot-checkpoint-2026-10-11.md).

The 80-record JEV/DeepSeek pilot is prepared in the existing private source run
`tmp/reenrich-2026-10-11`. No article downloads or paid provider requests were
performed during preparation. Production articles, dates, summaries, categories,
admission caches, weekly settings and retention were not changed.

## Frozen selection and source

The pilot retains all 52 freshly cached unresolved examples from the reviewed
92-record sample, including the twelve gap checks and negative controls. It adds
28 previously accepted diagnostic controls, retaining the six existing topic
strata and balancing comparison/model/application/business title strata. It
covers 60 hostnames. This deliberately selected sample cannot estimate corpus
accuracy or topic prevalence. The accepted controls are outside the production
recategorization scope; their saved content was not downloaded again.

JEV receives source title and up to 16,000 characters of saved source content.
Old and generated summaries are excluded. The ordinary relevance/admission
questions and conservative `legacy-cleanup-1` verdict rules are reused. The ten
accepted topic definitions and their order are frozen; topic confidence below
0.7 remains unclassified. Comparison is assessed independently, with confidence
below 0.7 left unknown. Other proposed formats and UI details remain pending.
No legacy category values or frozen reports are rewritten by this pilot.

DeepSeek processes only JEV accepts, using the same source. It returns a short
English summary plus exact supporting quotes, and separately grounded compared
product names for Comparison records. Quote presence is checked deterministically;
it is not proof of semantic entailment. Pilot review must assess factual support.
Summary evidence, model, prompt and request hashes are stored separately from
admission evidence; generating a summary cannot change the JEV cache key.

The user's preference is to use DeepSeek rather than Codex for article analysis.
Codex operates the tools and reads aggregates; source processing goes through
JEV/DeepSeek. Extra textual analysis requires the agreed monetary budget.

## Integrity and budget

Fresh offline cache verification again checked 3,533 saved responses with zero
errors. Inventory hash remains
`0c0e538bd91ac85323b9ce30d189c16b8cc55caaab42091ee3ce4320ef442c0e`.
The frozen source snapshot, original plan and reviewed sample retain their
handoff hashes. Pilot plan fingerprint:
`0ce41006e7dabebe468f6d8c249434e3a6ae502a7c5822ce6e2c227ba82d3b20`.
Pilot plan file SHA-256:
`af251a13e7cded1d7a126d7c65e7cdee9ed660e87b79c39b2d973530b2a7405f`.
The private pilot plan has mode 0600 inside the existing 0700 run directory.

| Planning amount for at most 80 requests each | JEV | DeepSeek | Total |
| --- | ---: | ---: | ---: |
| Rough characters/4 estimate, all 80 accepted | $0.01124 | $0.08390 | $0.09514 |
| Sum of conservative reservations, no returned usage | $0.21504 | $0.298375 | $0.513415 |
| Proposed pilot-only caps, awaiting confirmation | $0.25 | $1.25 | $1.50 |

Rates were rechecked against the official
[JEV model documentation](https://docs.typesafe.ai/models) and
[DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/).
JEV uses pinned `jev-1.13.0` at $0.042/M input tokens, free output. DeepSeek uses
`deepseek-flash`, non-thinking mode and at most 300 output tokens; calculations
use peak/cache-miss input $0.30/M and output $1.20/M. Account balances and
entitlements have not been checked. Estimates and usage-priced costs are not
provider invoices. No mass-processing budget is inferred.

Requests are serial, with no automatic retry. The SQLite journal commits a
reservation before dispatch, preserves received responses before answer parsing,
and enforces cumulative provider and total caps across restarts. Unknown billing,
missing usage, invalid answers, unexpected models and provider errors stop new
requests. Unknown usage keeps its reservation. Received valid responses replay
offline; failed/uncertain requests require operator review and are never silently
paid again. The run lock prevents concurrent pilot processes. Approval/caps and
the plan identity cannot be silently replaced after payment starts.

## Actual commands and receipts

Offline preparation, already executed:

```sh
rtk proxy env AINEWS_AUTH_SECRET=reenrich-local-validation-secret-32-chars \
  AINEWS_DATABASE_URL=sqlite:///./tmp/reenrich-tool-validation.db \
  ./venv1/bin/python scripts/reenrich_pilot.py prepare \
  --run-dir tmp/reenrich-2026-10-11
```

The paid command below is prepared but **has not been executed**. Run it only
after the user confirms these pilot monetary caps. It uses the ordinary private
provider-key configuration; the SQLite setting isolates application imports.
The note must describe the actual approval received, not this proposed budget.

```sh
rtk proxy env AINEWS_AUTH_SECRET=reenrich-local-validation-secret-32-chars \
  AINEWS_DATABASE_URL=sqlite:///./tmp/reenrich-tool-validation.db \
  ./venv1/bin/python scripts/reenrich_pilot.py run \
  --run-dir tmp/reenrich-2026-10-11 \
  --approved-total-usd 1.50 --approved-jev-usd 0.25 \
  --approved-deepseek-usd 1.25 \
  --approval-note 'REPLACE WITH ACTUAL USER BUDGET CONFIRMATION'
```

Private preparation artifacts: `pilot-plan.json`, `pilot-preparation.json`.
An earlier unpaid draft is preserved as `pilot-draft-<hash>.json`; the original
source plan/sample/cache were not replaced. A rubric draft can be refreshed
with `prepare --refresh-unpaid-plan` only before an approval/payment journal
exists and only while frozen source input identities remain unchanged.

The paid stage will create `pilot-budget-approval.json`, `pilot-journal.sqlite3`,
`pilot-results.json`, `pilot-usage.json` and `pilot-report.json` in the same run.
At this checkpoint the approval and payment journal do not exist. All source
text, model responses, comparison quotes and summaries remain private.

## Validation and next stop

Scoped synthetic/API regression suite: 85 passed, covering reservation limits,
restarts, unknown outcomes, saved error responses after interruption, source-only
evidence, conservative admission, unclassified topics and summary quote checks.
Existing JEV/admission/cleanup regression tests are included. Local tests use a
separate SQLite URL and complete placeholder auth configuration. The initial
test attempt supplied only an auth secret and failed eleven existing Settings
tests; rerunning with the complete isolated auth configuration passed.

Ruff passed for src/tests and both re-enrichment scripts; mypy passed for 143
source files (untyped function bodies follow the existing default mypy policy).
Scoped pylint passed at 10.00/10. Full `make lint`, full pytest, PostgreSQL
apply/restore rehearsal and live production preflight are not run at this
prepayment preparation stage; there is no commit, push, deployment or data apply.

Next step is the explicitly budgeted paid pilot. Stop after its results for
review of admission/topic/comparison/summary quality and usage, before any mass
processing. Keep the 441 fetch/quality-unresolved cases in the original operation
scope; this pilot does not reject or silently discard them.
