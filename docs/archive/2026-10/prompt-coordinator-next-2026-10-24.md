# Prompt: coordinator, next session (2026-10-24)

You continue as the **coordinator** for `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. The owner
writes in Russian; answer in Russian, short and plain.

1. Read `AGENTS.md`, your memory files and, from `origin/master` (`git fetch`; the main folder may
   lag), `docs/coordinator-state-2026-10-24.json` and the `owner_rules` of
   `docs/coordinator-state-2026-10-23.json`. Nothing else up front.
2. Check that the v0.1.126 deploy (run 40081695444) finished green and the app is healthy
   (`ssh ai-news`, read-only; `export APP_IMAGE=$(cat .last_deploy_image)` before any
   `docker compose run`). Report the state in three or four lines.
3. Then follow `next` in the state file: DEPLOY-126 (next night's logs), OPENAI-check on
   2026-10-26, ARCHIVE-week around 2026-10-30. B2 waits for the owner's go: if the owner says go,
   write the planner prompt for `specs/017-...` (file per AGENTS.md) and start it.
4. Executors: local sessions via ListAgents/SendMessage; if none is open, a background subagent
   (Agent tool, model sonnet) with the prompt saved to a file. Verify every report yourself (diff,
   CI, move check). Code PRs and tags need the owner's yes; docs/test PRs you may merge after green CI.
