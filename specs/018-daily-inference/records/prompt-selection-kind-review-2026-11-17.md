# Prompt: review of the `kind` question and event-only selection (2026-11-17)

Fresh read-only reviewer: do not edit, commit or push. Worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-018-kind` (uncommitted; `git -C <wt> diff`,
`git -C <wt> status --short` for new files). Task: `prompt-selection-kind-2026-11-17.md`; report:
`report-selection-kind-2026-11-17.md`; plan and label check in the same records folder. Tests pass
on this code: do not rerun them; run a check only to confirm a finding (venv
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`, `PYTHONPATH=src`).

Check:
1. Production safety: the migration on PostgreSQL (`alembic upgrade head` in
   `scripts/deploy_prod.sh`; inspect-based "add if missing"; downgrade); the journal file names
   that now carry `world-change-2` (digest assessor `journal-{version}-{cap}`, world screen
   journal): does the daily cap still hold on the deploy day, and can a rerun of a past day
   re-ask Jev unexpectedly? Anything else that reads `WORLD_CHANGE_VERSION` (`bulletin_store.py`,
   world report, CLI) and changes behavior.
2. Selection: is `showable` used everywhere a story can be shown or counted (sections, reserve,
   incidents count, day headline, repeats listing)? Old rows with NULL kind. `numbers["kinds"]`.
3. Parsing: `kind` validation; the defaults on `WorldChange` (could a real answer ever come back
   without kind and be treated as an event?).
4. Docs true and short; test names exist; nothing stale about four questions.

Final message: verdict and findings (file:line, concrete case, fix), under 40 lines.
