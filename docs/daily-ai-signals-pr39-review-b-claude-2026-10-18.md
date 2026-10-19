# PR #39 review B (claude): web, security, job, production safety

- Reviewed SHA: `8f30549a07225b17d1f8a7187b1d4956b174ecb6` (`feat/006-daily-ai-signals`), detached worktree
  `../AI_PARSER-review-b-claude`, no `.env`, `PYTHONPATH=src`, `env -i PATH=/usr/bin:/bin`.
- Reviewer: Claude (Opus 5.5), read-only. No provider calls, no production access, no commits.

## What was run

| Check | Result |
| --- | --- |
| `bash -n scripts/*.sh` | OK |
| Scoped tests: `test_web_daily_signals_api`, `test_web_public_digest`, `test_public_api_write_auth`, `test_web_app`, `test_deepseek_digest`, `test_daily_signals_migration`, `test_semantic_admission_compose` | 102 passed |
| Full suite `venv1/bin/pytest` (clean env, no `AINEWS_TEST_POSTGRES_URL`) | 1130 passed, 10 skipped (all skips are PostgreSQL integration tests needing `AINEWS_TEST_POSTGRES_URL`; PG not run by this reviewer) |
| Job script harness: fake `docker`, `flock`, `timeout` on PATH; abs path, `sh scripts/...` from repo root, `sh ./...` from `scripts/`; publish fail; signals fail; `timeout` exit 124; no `timeout` on PATH; budget nearly / partly spent | All as documented (details under Verified OK) |
| Web probe (TestClient + scratch SQLite): stored payload with XSS strings in every text field and `javascript:` link; payload with `current_7d` set and `expected_7d: null` | XSS: nothing unescaped, `javascript:` link dropped. `expected_7d: null`: `/` returns **500** (B02) |
| Rollback probe: DB upgraded with PR head, then `alembic upgrade head` from `git archive origin/master` | `FAILED: Can't locate revision identified by 'b6d1f0a7c3e5'` (B01) |

Not run: `make lint`, PostgreSQL integration tests, live browser check of the JS (the client code was read, not executed), real `docker compose`.

## Findings

| ID | Severity | File:line | Defect | Failure scenario | Evidence | Suggested fix | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B01 | major | `docs/daily-signals.md:139-141`; PR description, "Migration" rollback row | The rollback steps do not say that `alembic downgrade a42b750d0c44` has to run with the **feature** image before the reverted code is deployed. A reverted image does not have the `b6d1f0a7c3e5` revision file. | Operator reverts the feature and runs `scripts/deploy_prod.sh` (or downgrades after deploying the old image). `deploy_prod.sh:235` starts the old app, then `:238` `alembic upgrade head` fails with `Can't locate revision 'b6d1f0a7c3e5'`. `set -eu` stops the deploy, so the prune (`:241`) and the final `up -d` are skipped. A downgrade attempted from the old image fails the same way. | Rollback probe above (old migrations against a DB at `b6d1f0a7c3e5`). | Spell out the order: (1) stop timers and app; (2) run `docker compose ... run --rm app alembic downgrade a42b750d0c44` **with the current (feature) image**; (3) deploy the revert. Or say that keeping the migration file in the revert is required. Also mention that "revert the UI commit only" needs no DB step. | confirmed |
| B02 | minor | `src/app/web/app.py:496-501`, `src/app/web/signals_view.py:77-78` | The `/` route only catches `SQLAlchemyError` and `ValueError` around the signals render, so any other exception from `render_signals` returns 500. This breaks the "a signals error keeps `/` at 200" contract. | A stored payload that passes `DailySignalsResponse` validation (all trend counts are `Optional`) but has `current_7d` set and `expected_7d: null`. `f"{None:g}"` raises `TypeError` and `/?date=...` returns 500, while `/api/news/daily-signals` returns 200. Today's compute always sets both values, so this needs a hand-edited, older or future-methodology payload. | Probe: `/ with expected_7d=null: 500`, `api same day: 200`. | Catch `Exception` (log type only) in the `/` signals block, or render the 7-day branch only when both values are present (and print missing values as `-` instead of `None`). Add a regression test. | confirmed |
| B03 | minor | `docs/configuration.md:92-96`, `docs/daily-signals.md:96-97`, `docker-compose.prod.yml:54` | The docs present `AINEWS_DAILY_SIGNALS_COMPARABLE_FROM/MAX_CALLS/MAX_SECONDS/MAX_USD` as server `.env` settings. In production only `..._ENABLED` reaches the container: compose has no `env_file`, and `.env` is neither mounted nor copied into the image. | Owner sets `AINEWS_DAILY_SIGNALS_MAX_USD=0.20` in the server `.env` expecting a lower cap. The container still uses 0.50. The failure is in the safe direction for calls/USD, but `COMPARABLE_FROM` changes would also be ignored silently. | `docker-compose.prod.yml` environment block and volumes; `build/Dockerfile*` COPY lines (no `.env`). | Either state in both docs that only `ENABLED` is passed in production (use CLI `--max-usd`/`--max-calls` for overrides), or add the passthrough lines. Adding lines needs owner approval under AGENTS.md "Deploy And Ops". | confirmed |
| B04 | nit | `src/app/web/digest.html:490-500` | The client maps a network error or a 503 to `null`, which renders "not available for this date yet". The server render shows "temporarily unavailable" (`READ_ERROR`) in the same situation. | DB blip during a date change: the user sees "not available yet" for a day that has signals. | Code read. | Render `READ_ERROR` text when `!response.ok && response.status !== 422` or on catch. | confirmed |
| B05 | nit | `src/app/web/digest.html:610-621` | `loadSignals` runs only after a successful `/api/news/digests` response, so a failed digest fetch leaves the previous date's signals on screen. The digest race between two quick date changes (older response rendered last) was already there; signals guard against it, the digest does not, so the two blocks can show different dates. | Change the date while `/api/news/digests` returns 503: the date input shows the new date, the signals block still shows the old one. | Code read. | Call `loadSignals(selectedDate)` before the `response.ok` early return, or clear the block on failure. | confirmed (read) |
| B06 | nit | `src/app/web/app.py:186-190` | `__SIGNALS_CONTENT__` is substituted after `__DIGEST_CONTENT__`, so a digest text that contains the literal marker gets a second copy of the signals block. | Article title or summary containing `__SIGNALS_CONTENT__`. The inserted HTML is escaped server output, so this is cosmetic, not XSS. | Code read. | Substitute signals before the digest, or use one pass with a dict. | plausible |
| B07 | nit | `scripts/run_daily_digest_job.sh:15-22` | The re-exec handshake trusts inherited environment: `AINEWS_DAILY_JOB_LOCKED` set in the caller's environment skips `flock`, and in that case an inherited `REPORT_DATE` is used instead of `$1`. | Operator shell that exported these while debugging, then runs the script by hand: no host lock, possible overlap with auto-update. Not reachable from the systemd unit. | Harness run with `AINEWS_DAILY_JOB_LOCKED=1` went straight to `docker` without `flock`. | Pass the marker as an argument (`sh script --locked`) or check a value unique to this run (for example the PID of the parent). | confirmed (requires manual env) |
| B08 | nit | `scripts/deploy_prod.sh:235-238` | The new app starts before `alembic upgrade head`, and `/` and `/api/news/daily-signals` call `create_all()`. A request that runs `create_all()` at the same moment as the migration's inspect/create can make `op.create_table` fail with "already exists". | The first deploy aborts at `:238`. Recovery is safe: `create_all()` runs in one transaction (atomic on PG), and the migration skips existing tables and indexes (parity test), so rerunning `alembic upgrade head` / the deploy finishes. The window is milliseconds. | Code read; `test_upgrade_from_previous_head_matches_models` proves the post-`create_all` upgrade path. | Optional: add one sentence to `docs/daily-signals.md` ("if the deploy stops at alembic, rerun it; the migration is idempotent"). | plausible |

## Verified OK

- **XSS, server side** (`signals_view.py`): every text field (`name`, `type`, `vendor`, `variant_of`,
  `variants`, `novelty_quote`, story `label`, event labels, notes, link `title`/`publisher`) goes through
  `html.escape` (quote=True). `href` is escaped and only `^https?://` links are rendered. Numbers come
  from validated int/float fields. Card ids are constants. No JSON is embedded in the HTML. The probe with
  `"><img onerror>` / `<script>` / `javascript:` payloads found no unescaped output.
- **XSS, client side** (`digest.html`): `escapeHtml` escapes `& < > " '`. All untrusted strings go
  through it, including the `href` attribute. Links are filtered with the same http(s) regex. The
  coverage line and the trend counts come from the `response_model`-validated API (ints/floats), and the
  coverage text is escaped again by `signalStatus`.
- **Payload exposure**: `DailySignalsResponse.model_validate` ignores extra stored keys, so only the
  modelled fields are public. These are entity names, counts, public article URLs/titles, the
  url->event_type map, thresholds and coverage counters. No admin or operator data, no costs, no
  provider details.
- **Auth**: only `GET`/`HEAD` on the exact path `/api/news/daily-signals` was added to
  `is_public_news_api`. Other methods with auth enabled are covered by
  `test_public_api_write_auth.py:186`. The publish token set is unchanged. No other path became public.
- **Request path**: `_read_daily_signals` is one `select ... where report_date = ?` on a unique index,
  plus JSON parse and validation. No provider imports or calls on the path. Missing table, DB error or
  invalid JSON → `unavailable`/`READ_ERROR` and `/` stays 200 (tested). The B02 gap is the only
  exception.
- **Client race**: `loadSignals` drops responses whose date is no longer selected. The initial render is
  server-side, so the first load needs no extra fetch. The mobile breakpoint collapses `.signal-grid`
  to one column, and `overflow-wrap: anywhere` covers long names and URLs.
- **Job script**:
  - Report date is resolved once (UTC yesterday, same rule as `daily-publish`'s default) and exported
    across the `flock` re-exec.
  - Single lock and wait unchanged (`flock -w 7200` on the same path).
  - Re-exec uses the absolute `$SCRIPT_DIR` and works from any cwd.
  - The publish exit code decides the job (harness: `PUB_RC=3` → rc 3, no signals call).
  - Signals failure or timeout (rc 1 / 124) → message, `docker rm -f ai-news-signals-<date>`, rc 0.
  - No `timeout` binary → runs without the outer limit, app `--max-seconds` still applies.
  - Budget: the start time is taken before the lock wait. `elapsed + remaining + 600 reserve` stays
    `<= 14400` (`TimeoutStartSec`), and the 30 s `-k` grace fits in the reserve. Skip below 300 s;
    `--max-seconds = remaining - 180`. Harness: 12000 s elapsed → `timeout -k 30 1800`,
    `--max-seconds 1620`; 13600 s → skipped, rc 0.
  - `$limit` unquoted by design. Other expansions are quoted. `set -eu` holds (`$limit` is always set).
- **Compose and settings**: one added line, `AINEWS_DAILY_SIGNALS_ENABLED: ${...:-false}`. Defaults
  are false / 200 / 2700 / 0.50, and the USD validator only rejects malformed values. Ports, auth,
  retention, DB, Caddy, `deploy/`, the systemd unit and timers, and `deploy_prod.sh` are unchanged.
- **Migration**: additive. Creates are idempotent after `create_all()`, and index names match the ORM
  (parity test passes). Downgrade drops only the six new tables. An old image running against the new
  schema works (unknown tables are ignored; the old legacy-cleanup guard refuses on the unknown FKs,
  which is the safe direction; PG cascades handle prune).
- **Logs and reports**: the error logs carry only the date and the exception type. The run report is
  written under `data/daily-signals/runs/` (dir 0700, `private_write`). The ledger is opened 0600 with
  `fchmod`.

## Verdict

**Merge after fixes**: B01 (rollback order in the docs and PR description) and B02 (catch-all
isolation on `/` plus a regression test). B03 is a docs correction. B04-B08 are optional.
