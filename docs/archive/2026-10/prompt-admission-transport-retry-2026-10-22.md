# Prompt: a Jev transport failure holds one candidate, not the whole day (2026-10-22)

You are the implementer for `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. Read `AGENTS.md` first and
follow it. Work only in the worktree below; do not write to git in the main folder.

## Incident (already diagnosed, read-only)

- Nightly fetch `run_id 20261022010003` (prod, v0.1.114): one Jev admission call ended with
  `httpx.ReadTimeout` (`AINEWS_JEV_TIMEOUT_SECONDS=3`). The daily admission journal
  (`data/daily-admission/2026-10-22/journal.sqlite3`, built in `src/app/core/jev.py`
  `jev_relevance_scorer`) recorded it as `state=failed, error_type=ReadTimeout`, billing unknown.
- `PilotJournal` is created there WITHOUT `transport_review_reason`, so the next call raised
  `PilotStopped("unknown_or_failed_previous_call_requires_review")`, logged as
  `jev_screening_unavailable error_type=PilotStopped`; the cycle paused and the site shows
  `PAUSED_MESSAGE`. Only 3 sources were processed. Every further run that UTC day stops the same way.
- The daily enrichment journal had the same gap and was fixed in `src/app/core/daily/enrichment.py`
  (`TRANSPORT_REVIEW_REASON`, `TRANSPORT_RETRY_DELAYS`; troubleshooting case
  `daily-digest-dropped-provider-connection`). Apply the same mechanism to the admission journal.

## Setup

```
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch origin
git worktree add ../AI_PARSER-wt-admission-retry -b fix/admission-transport-retry-20261022 origin/master
cd ../AI_PARSER-wt-admission-retry
```

Checks in the worktree: `PYTHONPATH=src ../AI_PARSER/venv1/bin/python ...` and
`PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest ...`.

## Steps (doc first, then code and tests)

1. `src/app/core/ingestion/pipeline.md` (doc first):
   - add `  - src/app/core/jev.py` and `  - src/app/storage/reenrich_pilot_journal.py` to `covers:`;
   - in Behavior, before the rule "Screening unavailable (provider error, timeout, invalid admission
     answer)" (around line 247), add the rules below and narrow that rule to "provider error
     (HTTP error answer such as 5xx after the journal's overload retries, auth error), invalid
     admission answer, or `ADMISSION_CONSECUTIVE_TRANSPORT_LIMIT` transport failures in a row":
     - With the daily admission journal (`daily_enrichment_enabled`), a transport failure of a Jev
       call (timeout or dropped connection: the error types accepted by
       `PilotJournal.review_transport_failure`; per-request timeout `jev_timeout_seconds`) keeps its
       reservation, is reviewed with `ADMISSION_TRANSPORT_REVIEW_REASON` and retried once after
       `ADMISSION_TRANSPORT_RETRY_DELAYS`.
     - If the retry also fails, that candidate is unresolved: it stays `pending` (replayed by the next
       run like any pending candidate), no decision is cached, the run goes on with the next
       candidate. Only `ADMISSION_CONSECUTIVE_TRANSPORT_LIMIT` such candidates in a row (no
       successful Jev answer between them) pause the run. A successful answer resets the count.
     - A candidate whose retries were already exhausted by an earlier run of the same UTC day is held
       the same way without sending a request and does not count toward the limit.
     - A failed row left by an older version (no review) is reviewed and retried the same way.
     Name the new tests (step 3) after each rule.
   - Decisions, one row: "A transport failure holds one candidate, not the day | one timeout paused
     collection for the whole UTC day (incident 2026-10-22); a timeout says nothing about the
     article, the candidate stays pending and is replayed. A provider error (5xx, auth) or 5
     timeouts in a row mean the service is down, so the run pauses (owner, 2026-10-22). One retry
     after 10 s, timeout 5 s: 3 s was too tight; 3938 journal calls 2026-10-12..22 all took 2 s or
     less."
2. Code:
   - `src/app/storage/reenrich_pilot_journal.py`: add
     `class TransportAttemptsExhausted(ValueError)` with an attribute `dispatched: bool` (a request
     was sent in this `call` invocation). Raise it (same message
     "Reviewed transport attempts exhausted; result unresolved") where `_attempt` now raises the
     plain `ValueError`. `call` must set `dispatched=True` when the exhaustion follows a request it
     sent itself (the recursive retry path), `False` when `_attempt` raises before any dispatch in
     this invocation. Subclassing `ValueError` keeps daily enrichment unchanged; run
     `tests/unit/test_daily_enrichment.py` to prove it.
   - `src/app/core/jev.py`: module constants
     `ADMISSION_TRANSPORT_REVIEW_REASON = "daily-admission: transport failure, conservative reservation kept"`,
     `ADMISSION_TRANSPORT_RETRY_DELAYS = (10,)`, `ADMISSION_CONSECUTIVE_TRANSPORT_LIMIT = 5`.
     Pass the first two to `journal_class(...)` (`transport_review_reason=`,
     `transport_retry_delays=`); journal identity and caps stay the same, so today's journal file
     still opens. In `JevRelevanceScorer.classify` catch `TransportAttemptsExhausted` before the
     generic `except`: set `self.input_held = True`, do NOT set `self.failed`, log
     `jev_transport_held` (`{"dispatched": ...}`, no secrets), and if `dispatched` increment
     `self.consecutive_transport_failures`; when it reaches the limit set `self.failed = True`,
     `self.input_held = False`, log `jev_screening_unavailable` with
     `error_type="TransportAttemptsExhausted"` and return `None` (the pipeline then pauses as now).
     Reset the counter to 0 after every successful answer. The pipeline needs no change if it keeps
     treating `input_held` as "unresolved, stays pending" (check `_admit` around
     `src/app/core/ingestion/pipeline.py:311`; if it does need one, keep it minimal).
   - The path without a journal (daily enrichment off) is unchanged; say so in the doc rule.
3. Tests in `tests/unit/test_semantic_admission_pipeline.py` (reuse `Scenario` and the `scorer`
   contextmanager pattern of `test_oversized_journal_input_stays_pending_without_pausing_other_articles`,
   build the journal with the constants from `app.core.jev`, monkeypatch
   `app.storage.reenrich_pilot_journal.time.sleep` to record delays; add items to the scenario if
   it has too few for the limit tests):
   - `test_admission_timeout_is_retried_once_without_pausing`: first request `httpx.ReadTimeout`,
     retry answers; not paused, sleeps `== [10]`, journal report one `reviewed_transport` call.
   - `test_admission_timeout_twice_holds_only_that_candidate`: both attempts for one candidate time
     out, others answer; not paused, that candidate `pending` and counted in `semantic_unresolved`,
     the others decided, exactly 2 requests for that candidate.
   - `test_admission_consecutive_timeouts_pause_run`: every request times out; the run pauses
     (`screening_paused == 1`, `CollectionStatus.paused`) after exactly
     `ADMISSION_CONSECUTIVE_TRANSPORT_LIMIT` candidates (2 requests each), no further requests.
   - `test_admission_success_resets_timeout_count`: limit-1 candidates time out, one answers,
     limit-1 time out again; not paused.
   - `test_exhausted_candidate_from_earlier_run_is_held_without_request`: run once with one
     candidate failing both attempts, run again the same day: no request for it, it stays pending,
     counter not incremented.
   - `test_failed_admission_row_from_older_version_is_retried`: a `failed`/`ReadTimeout` row made
     with a journal built WITHOUT the reason (old behavior), then a run with the new constants and a
     healthy mock: not paused.
   - `test_admission_server_error_still_pauses_at_once`: Jev answers HTTP 500 (non-overload); run
     pauses on the first candidate.
   If a test cannot be built this way, say why in the report; do not weaken an assertion.
3a. Jev timeout 3 -> 5 seconds (owner request 2026-10-22). Change exactly these three lines:
   - `docker-compose.prod.yml:43`: `${AINEWS_JEV_TIMEOUT_SECONDS:-3}` -> `${AINEWS_JEV_TIMEOUT_SECONDS:-5}`
     (prod has no override in its `.env`, so this default is what prod uses);
   - `src/app/config/settings.py:46`: `default=3.0` -> `default=5.0`;
   - `docs/configuration.md:22`: `AINEWS_JEV_TIMEOUT_SECONDS=3` -> `AINEWS_JEV_TIMEOUT_SECONDS=5`.
   Mention the timeout in the pipeline.md rule from step 1 by name (`jev_timeout_seconds`), not the number.
4. `docs/troubleshooting.md`: add a case `admission-jev-timeout-pauses-day` (same JSON shape as
   `daily-digest-dropped-provider-connection`): symptom (site notice, `jev_screening_unavailable
   error_type=PilotStopped`), evidence (journal row above, `logs/daily-fetch.log` run
   20261022010003), cause, fix, verification (the new test names).
5. Checks:
   ```
   PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest tests/unit/test_semantic_admission_pipeline.py tests/unit/test_code_docs.py tests/unit/test_daily_enrichment.py tests/unit/test_reenrich_pilot.py tests/unit/test_weekly_transport_recovery.py
   PYTHONPATH=src ../AI_PARSER/venv1/bin/python scripts/check_code_docs.py --diff origin/master --strict
   make lint PYTHON=../AI_PARSER/venv1/bin/python
   PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest
   ```
   All must pass. Keep files ASCII.
6. Commit (one commit):
   ```
   git add -A
   git commit -m "fix(admission): a Jev timeout holds one candidate instead of pausing the day" -m "One ReadTimeout on 2026-10-22 left a failed row in the daily admission journal and paused collection for the whole UTC day. Transport failures are now retried once; a candidate that still fails stays pending and the run goes on. Five such candidates in a row, a provider error or an invalid answer still pause. Jev timeout default 3 -> 5 s." -m "Co-Authored-By: <your model name> <noreply@anthropic.com>"
   git push -u origin fix/admission-transport-retry-20261022
   gh pr create --base master --head fix/admission-transport-retry-20261022 \
     --title "fix(admission): a Jev timeout holds one candidate instead of pausing the day" \
     --body "Incident 2026-10-22: one Jev ReadTimeout paused news collection for the day (journal row failed/ReadTimeout, then PilotStopped). Now: one retry after 10 s (ADMISSION_TRANSPORT_RETRY_DELAYS), then the candidate stays pending and the run goes on; ADMISSION_CONSECUTIVE_TRANSPORT_LIMIT=5 such candidates in a row, a provider error (5xx, auth) or an invalid answer still pause. Jev timeout default 3 -> 5 s (owner request). Doc: src/app/core/ingestion/pipeline.md (covers core/jev.py now). Troubleshooting case added. Gate: make lint + full pytest run (paste results)."
   ```
   Replace the Co-Authored-By line with your real model name and its real address; if you have
   none, drop the line.

## Report (all fields required)

- PR link; branch; commit SHA.
- `git diff --stat origin/master`.
- Output tail of each check in step 5 (pass/fail counts).
- Any deviation from these steps and why.
- Open questions, one line each (AGENTS.md "Owner And Questions").

Do not merge, do not tag, do not touch prod.
