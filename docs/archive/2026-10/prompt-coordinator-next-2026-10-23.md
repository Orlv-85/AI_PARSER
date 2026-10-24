# Prompt: coordinator, next session (2026-10-23)

You continue as the **coordinator** for `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. The owner
writes in Russian; answer in Russian, short and plain.

1. Read `AGENTS.md`, your memory files and `docs/coordinator-state-2026-10-23.json` on
   `origin/master` (`git fetch; git show origin/master:docs/coordinator-state-2026-10-23.json`;
   the main folder may lag behind master). Nothing else up front.
2. Report the state in three or four lines (prod v0.1.120, no open PRs, what is next).
3. Check today's scheduled runs of `nightly-health` and `db-maintenance` (`gh run list --workflow ...`;
   GitHub delays schedules here by about 5 h). Report one line.
4. Ask the owner one question: give spec 016 phase 1 (archive tables + prune archives before
   delete, `specs/016-article-archive/tasks.md`) to session `ai-parser-12` now? Recommended yes:
   every deploy prunes articles older than 800 days and loses their text.
5. Then follow `next` in the state file (2026-10-24 morning: Rising/Cooling on `/`; 2026-10-26:
   OpenAI/TLDR unresolved share after #86/#88).
6. You hand out prompts to local sessions yourself (ListAgents, SendMessage with
   notify_when_idle); the owner does not duplicate them. Write a prompt only after reviewing the
   previous PR; save every prompt to a file per `AGENTS.md`.
