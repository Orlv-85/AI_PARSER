# Documentation index

## Code docs (live next to the code)

Technical maps owned by the code: flow, modules, tables, versions, invariants, where to change what.
Updated in the same change as the code (AGENTS.md, "Feature Docs Next To Code"); checked by
`scripts/check_code_docs.py` (pytest + CI).

| Feature | Doc | Main module |
| --- | --- | --- |
| System overview | [src/app/README.md](../src/app/README.md) | - |
| Daily AI Signals (006, 007) | [src/app/core/daily_signals.md](../src/app/core/daily_signals.md) | `src/app/core/daily_signals.py` |

## General

| Doc | Covers |
| --- | --- |
| [deploy.md](deploy.md) | Docker, CI/CD, server setup, daily jobs, maintenance, systemd |
| [configuration.md](configuration.md) | Environment variables, Jev admission, `sources.yaml` |
| [cli.md](cli.md) | CLI commands, fetch/cron, search, MCP server, prune |
| [troubleshooting.md](troubleshooting.md) | Known failures with cause and fix (JSON cases) |
| [daily-signals.md](daily-signals.md) | Daily AI Signals operator guide: commands, cost, deploy note, rollback |
| [weekly-analytics.md](weekly-analytics.md) | Weekly attention analytics v2: worker, budgets, rollback |
| [article-reenrichment.md](article-reenrichment.md) | Article dates and re-enrichment operator guide |
| [article-source-cache.md](article-source-cache.md) | Unpaid article source evidence cache |

## Backlog

- [backlog-todo.json](backlog/backlog-todo.json) - product backlog after 007
- [article-archive-todo.json](backlog/article-archive-todo.json) - off-site backups, full-text archive
- [jev-novelty-second-opinion-todo.json](backlog/jev-novelty-second-opinion-todo.json) - Jev for New

## History

Dated records (`prompt-<task>-<date>.md`, `*-review-*`, `*-results-*`, `*-report-*`,
`*-checkpoint-*`) are history, not references:

- records of a feature live next to its spec: `specs/<NNN>-<name>/records/`;
- other records: `docs/prompt-<task>-<date>.md` while open, then `archive/<YYYY-MM>/`;
- [archive/2026-10/](archive/2026-10/) - re-enrichment, semantic admission, cleanups, audits;
  [archive/2026-10-10-12/](archive/2026-10-10-12/README.md) - session materials of Oct 10-12.

Feature specs live in `specs/` (one root); `.specify/` holds only Spec Kit tooling.
