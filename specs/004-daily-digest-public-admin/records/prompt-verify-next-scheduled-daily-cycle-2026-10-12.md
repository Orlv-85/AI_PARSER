# Verify the next scheduled daily cycle

Work in /Users/vyacheslavorlovskiy/GitHub/AI_PARSER. Communicate in Russian; summaries and product categories remain English. Read AGENTS.md, /Users/vyacheslavorlovskiy/.codex/RTK.md, and specs/004-daily-digest-public-admin/records/daily-cycle-verification-results-2026-10-12.md first. Shell commands must use rtk.

User preference: save every task/handoff prompt for another session in a separate docs/prompt-<task>-<date>.md file before delivering it, include its clickable link, and preserve this preference in future context/handoffs. Preserve existing untracked user files and the user's AGENTS.md edit; never stage them automatically.

The first scheduled cycle on October 12 ran: fetch at 01:00 UTC completed with exit 0 but paused screening after a local oversized input; digest at 02:00 UTC failed with invalid_daily_assessment. A manual October 11 resume published one grounded English summary over scope 11, holding 10. That resume does not establish a successful automatic publication.

PR #20 / v0.1.84 fixed partial ingestion proof handling and bounded robots redirects. PR #21 / v0.1.85 distinguishes a local JEV input bound from provider outage: oversized input stays pending, all real outage/schema/budget failures retain their existing safeguards. See the result document and actual server receipts for final deployment and collection status.

The next expected real scheduled cycle is October 13 at 01:00 UTC fetch and 02:00 UTC digest, serving October 12 UTC. Verify server UTC, deployed image/migration, effective systemd units and timer LAST timestamps, service execution timestamps and exit codes, private logs, complete report scope, counts/holds, known usage/cost, public API and browser page. A manual run is not automatic evidence. If this time has not arrived, record that fact and do not wait for hours or change the timers.

Private operation receipts: /opt/ai-news/backups/daily-cycle-20261012/. Daily reports/journals: /opt/ai-news/data/daily-enrichment/2026-10-10/ and /opt/ai-news/data/daily-enrichment/2026-10-11/. Source/date recovery and rollback: /opt/ai-news/data/daily-enrichment/hold-recovery-2026-10-12/. Admission journal: /opt/ai-news/data/daily-admission/2026-10-12/journal.sqlite3. SSH helper tmp/legacy_cleanup_ops.py reads stored credentials without printing them.

October 10 scope is now 48 with 7 summaries and 41 holds. Two Cognition entries were proved to belong to July 1 and June 29 and corrected with a private rollback backup. Other historical digest reports were not rewritten. Do not resummarize supported rows, redispatch compatible paid responses, repeat mass cleanup, lower admission/grounding/date requirements, or change auth, weekly-off, retention 800 days or 5/4 GiB thresholds. Only retry a hold when new usable evidence or a concrete technical fix warrants it. Source extraction is code; textual analysis uses JEV/DeepSeek. Keep private HTML/corpus/provider responses/secrets out of context/log output/Git.

For code changes, read relevant specs; use apply_patch; read dev-quality-gate before commit/push; run full make lint and full venv1 pytest with isolated SQLite/PostgreSQL, then PR and regular release. Production is never a test database. The latest full local gate was 854 passed, zero skipped, coverage 91.38%; tracked CI excludes four unrelated untracked user tests.

Final report must state whether a successful real scheduled publication is confirmed, for which UTC day; actual failures/remaining holds and reasons; code/PR/release/image and checks; incremental/cumulative known spend; private receipt paths. Do not declare completion from a green deploy or a manual run.
