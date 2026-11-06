# Prompt (Codex, gpt-6-astra high): review of PR #215, world story not repeated (2026-11-06)

Repo `ai-news-collector`, worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/world-no-repeat`, branch
`fix/018-world-no-repeat` (one commit on origin/master). Read-only review: do not edit code, do not
commit, push or use gh; no network; no sub-agents.

Task given to the executor: `specs/018-daily-inference/records/prompt-world-no-repeat-codex-2026-11-05.md`
(the rule is there). Executor report: `specs/018-daily-inference/records/report-world-no-repeat-2026-11-05.md`.
The coordinator changed after the executor: the candidate title is compared as
`cluster_key(digest_title(item.title))` (the stored title is `digest_title` of it), and the code
map row was merged into the `bulletin_input.py` row.

Review `git diff origin/master -- src tests` and the doc `src/app/core/bulletin/builder.md`:

1. Does the code do exactly the rule (D-1 only, ready rows only, all four sections, URL or title
   key, digest candidates untouched, unreadable payload leaves all eligible)? Any case where a
   story still repeats on D, or a world story is wrongly dropped?
2. Payload shape: check against `src/app/storage/bulletin_store.py` / `bulletin_store.md` and
   the builder's stored story fields that `key_results`, `cooperation`, `rubric_story`,
   `incident_story`, `title`, `links[].url` are what is stored. Is a missing section key possible
   on real ready rows (older payload versions)? If so, would the broad except hide the whole rule?
3. Import of `BulletinRepo` into `bulletin_input.py`: any import cycle or layering problem?
4. Tests: do they test the rule honestly (not the implementation), and is anything important
   untested? Doc: does Behavior match the code; are the test names real?

Run only: `env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_bulletin_builder.py`.

Write `specs/018-daily-inference/records/review-world-no-repeat-2026-11-06.md`: verdict (approve /
changes needed), findings ranked by severity with file:line and a concrete failing scenario,
and minor notes separately. Keep it short.
