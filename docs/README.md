# Documentation index

## Code docs (live next to the code)

Intended current behavior of a feature, its decisions, invariants and code map. Changed first, then
the code (AGENTS.md, "Feature Docs Next To Code"); checked by `scripts/check_code_docs.py` (pytest + CI).
Specs in `specs/` are the history of how a feature got there.

| Feature | Doc | Main module |
| --- | --- | --- |
| System overview | [src/app/README.md](../src/app/README.md) | - |
| Daily digest enrichment | [src/app/core/daily/enrichment.md](../src/app/core/daily/enrichment.md) | `src/app/core/daily/enrichment.py` |
| Daily AI Signals (006, 007) | [src/app/core/daily/signals.md](../src/app/core/daily/signals.md) | `src/app/core/daily/signals.py` |
| Period AI Signals (017) | [src/app/core/periodic/signals_period.md](../src/app/core/periodic/signals_period.md) | `src/app/core/periodic/signals_period.py` |
| Fetch pipeline (001, 002, admission) | [src/app/core/ingestion/pipeline.md](../src/app/core/ingestion/pipeline.md) | `src/app/core/ingestion/pipeline.py` |
| Source onboarding (003, 011) | [src/app/core/sources/onboarding.md](../src/app/core/sources/onboarding.md) | `src/app/core/sources/onboarding.py` |
| Article archive (016) | [src/app/core/archive/capture.md](../src/app/core/archive/capture.md) | `src/app/core/archive/capture.py` |
| Web pages and static assets | [src/app/web/pages.md](../src/app/web/pages.md) | `src/app/web/routes/pages.py` |

## General

| Doc | Covers |
| --- | --- |
| [deploy.md](deploy.md) | Docker, CI/CD, server setup, daily jobs, maintenance, systemd |
| [configuration.md](configuration.md) | Environment variables, Jev admission, `sources.yaml` |
| [cli.md](cli.md) | CLI commands, fetch/cron, search, prune |
| [troubleshooting.md](troubleshooting.md) | Known failures with cause and fix (JSON cases) |
| [daily-signals.md](daily-signals.md) | Daily AI Signals operator guide: commands, cost, deploy note, rollback |

## Backlog

- [backlog-todo.json](backlog/backlog-todo.json) - product backlog after 007
- [article-archive-todo.json](backlog/article-archive-todo.json) - off-site backups, full-text archive
- [jev-novelty-second-opinion-todo.json](backlog/jev-novelty-second-opinion-todo.json) - Jev for New
- [tooling-todo.json](backlog/tooling-todo.json) - agent tooling (spec pipeline), not product
- [coordinator-todo.json](backlog/coordinator-todo.json) - coordinator checks, fixes and open decisions

## Work in progress

[work/](work/) - open process files: the coordinator state and, git-ignored, active prompts for
other sessions (`work/prompt-<task>-<date>.md`).

## History

Dated records (prompts, plans, reports, reviews, old coordinator states) are history, not
references. Nothing dated stays in the root of `docs/`:

- records of a feature live next to its spec: `specs/<NNN>-<name>/records/`;
- other records: `work/` while open, then `archive/<YYYY-MM>/`;
- [archive/2026-10/](archive/2026-10/) - re-enrichment, semantic admission, cleanups, audits,
  module split plans, summary pilots (Jev entailment, repair, grounding), the Codex multi-agent
  guide; [archive/2026-10-10-12/](archive/2026-10-10-12/README.md) - session materials of Oct 10-12.

Feature specs live in `specs/` (one root); `.specify/` holds the Spec Kit templates (format of new
specs) and Codex-era tooling kept for history.
