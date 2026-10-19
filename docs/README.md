# Documentation index

## Code docs (live next to the code)

Technical maps owned by the code: flow, modules, tables, versions, invariants, where to change what.
Updated in the same change as the code (AGENTS.md, "Feature Docs Next To Code").

| Feature | Doc | Main module |
| --- | --- | --- |
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

- [backlog-todo.json](backlog-todo.json) - product backlog after 007
- [article-archive-todo.json](article-archive-todo.json) - off-site backups, full-text archive
- [jev-novelty-second-opinion-todo.json](jev-novelty-second-opinion-todo.json) - Jev for New

## History

Dated files in this folder are records, not references: `prompt-<task>-<date>.md` (prompts for
other sessions), `*-review-*`, `*-results-*`, `*-report-*`, `*-checkpoint-*`; older ones in
`archive/`. Feature specs live in `.specify/specs/`.
