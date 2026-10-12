# Archived session materials, 2026-10-10–12

These are historical prompts, reviews, checkpoints and contexts. They preserve the original requirements and receipts; **do not resume their commands or infer current approvals, budgets, branches or production settings from them**. Contradictory intermediate states are retained as history.

The archive mirrors original repository-relative paths. Shell commands, plain paths and JSON fields inside records describe their original location and execution time. Markdown links to available documents have been adjusted for the archive location. Private cache/journal/backup paths are recovery pointers; their contents are excluded from Git.

## Completed outcomes

- Semantic admission and PR #13 review fixes: [contract](../../semantic-admission-spec-2026-10-10.md), [activation](../../semantic-admission-production-activation-2026-10-10.md); final reviewed head `dece005`.
- Production screening flags and weekly-off: PR #14, `30e3eb4`.
- Legacy cleanup and retention 800: [outcome](../../legacy-articles-jev-cleanup-2026-10-11.md), PR #15, `c787ce0`.
- Re-enrichment/date repair: [outcome](../../reenrich-production-results-2026-10-11.md), implementation delivered in PR #16, `4e46089`. The old context claims about uncommitted code and missing mass approval are superseded.
- Daily publication: [October 11 receipt](../../daily-publication-results-2026-10-11.md) and [October 12 receipt](../../daily-cycle-verification-results-2026-10-12.md). Later receipts take precedence; manual resume does not establish successful automatic publication.
- Historical weekly pilot: read the [later session report](weekly-pilot-session-report-2026-10-10.md) after the [earlier diagnostic](specs/010-weekly-ai-analytics-for-management-dashboard/historical-backfill-diagnostic.md). The report records subsequent publication and cancelled UI work. Runtime states apply only to the recorded time; weekly remains off under the later production policy.

## Remaining work

The historical preview runner and its four mock tests are preserved below as unsupported pilot snapshots, outside the active `scripts/` and `tests/` trees. Their contents and mirrored relative layout are unchanged. The runner reserves narrative cost using `weekly_output_token_cap` (1200 by default), while the current adapter uses `weekly_narrative_output_token_cap` (2400 by default); its four mock tests bypass narrative generation and do not establish readiness for new paid runs. The maintained frozen-report entrypoint is `scripts/weekly_frozen_report.py`.

The [next scheduled-cycle verification prompt](../../prompt-verify-next-scheduled-daily-cycle-2026-10-12.md) and [weekly editorial prototype prompt](../../prompt-weekly-editorial-prototype-2026-10-12.md) remain outside the archive as separate pending tasks. This archival cleanup does not execute either task. The [weekly stage index](../../weekly-report-stages-2026-10-12.md) points to the specific frozen-v4 stage-3 handoff. The completed narrative task is recorded in the [repair/delivery results](../../weekly-narrative-repair-results-2026-10-12.md), including the v0.1.89 UI follow-up.

Local private source caches, paid responses, journals, receipts and backups remain under their existing ignored paths. Do not reset or regenerate them to understand the archive.

## Inventory

| Historical record | Status |
|---|---|
| [docs/pr-13-review-2026-10-10.md](docs/pr-13-review-2026-10-10.md) | Superseded prompt/context or completed-stage receipt |
| [docs/semantic-admission-agent-prompt-2026-10-10.md](docs/semantic-admission-agent-prompt-2026-10-10.md) | Superseded prompt/context or completed-stage receipt |
| [docs/prompt-persist-production-screening-2026-10-11.md](docs/prompt-persist-production-screening-2026-10-11.md) | Superseded prompt/context or completed-stage receipt |
| [docs/prompt-cleanup-legacy-articles-jev-2026-10-11.md](docs/prompt-cleanup-legacy-articles-jev-2026-10-11.md) | Superseded prompt/context or completed-stage receipt |
| [docs/prompt-retention-800-days-2026-10-11.md](docs/prompt-retention-800-days-2026-10-11.md) | Superseded prompt/context or completed-stage receipt |
| [session-context-2026-10-10.json](session-context-2026-10-10.json) | Superseded prompt/context or completed-stage receipt |
| [docs/prompt-reenrich-and-fix-publication-dates-2026-10-11.md](docs/prompt-reenrich-and-fix-publication-dates-2026-10-11.md) | Superseded prompt/context or completed-stage receipt |
| [docs/prompt-resume-2026-10-11.md](docs/prompt-resume-2026-10-11.md) | Superseded prompt/context or completed-stage receipt |
| [docs/prompt-resume-reenrich-2026-10-11.md](docs/prompt-resume-reenrich-2026-10-11.md) | Superseded prompt/context or completed-stage receipt |
| [docs/prompt-fix-daily-publication-2026-10-11.md](docs/prompt-fix-daily-publication-2026-10-11.md) | Superseded prompt/context or completed-stage receipt |
| [docs/prompt-verify-daily-cycle-and-resolve-holds-2026-10-11.md](docs/prompt-verify-daily-cycle-and-resolve-holds-2026-10-11.md) | Superseded prompt/context or completed-stage receipt |
| [docs/reenrich-stage-checkpoints-2026-10-11.md](docs/reenrich-stage-checkpoints-2026-10-11.md) | Superseded prompt/context or completed-stage receipt |
| [session-context-reenrich-2026-10-11.json](session-context-reenrich-2026-10-11.json) | Superseded prompt/context or completed-stage receipt |
| [specs/010-weekly-ai-analytics-for-management-dashboard/historical-backfill-diagnostic.md](specs/010-weekly-ai-analytics-for-management-dashboard/historical-backfill-diagnostic.md) | Historical pilot receipt; later follow-ups are separate |
| [weekly-pilot-session-report-2026-10-10.md](weekly-pilot-session-report-2026-10-10.md) | Historical pilot receipt; later follow-ups are separate |
| [docs/prompt-assess-weekly-preview-readiness-2026-10-12.md](docs/prompt-assess-weekly-preview-readiness-2026-10-12.md) | Superseded by the four-stage weekly delivery flow |
| [docs/prompt-deliver-weekly-report-2026-10-12.md](docs/prompt-deliver-weekly-report-2026-10-12.md) | Superseded as a single-run task by the four-stage flow |
| [docs/prompt-fix-weekly-narratives-2026-10-12.md](docs/prompt-fix-weekly-narratives-2026-10-12.md) | Completed task; see the current repair/delivery results |
| [scripts/weekly_historical_preview.py](scripts/weekly_historical_preview.py) | Unsupported historical pilot runner snapshot |
| [tests/unit/test_weekly_historical_preview.py](tests/unit/test_weekly_historical_preview.py) | Four historical mock tests; outside normal pytest discovery |

## Continuing user preference

Every future task/handoff prompt for another session must be saved to `docs/prompt-<task>-<YYYY-MM-DD>.md` before delivery, linked in the response, and carried into future contexts/handoffs. See [AGENTS.md](../../../AGENTS.md).
