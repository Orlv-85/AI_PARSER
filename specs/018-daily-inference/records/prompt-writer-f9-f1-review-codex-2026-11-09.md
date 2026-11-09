# Prompt (Codex, gpt-6-astra high): review of PR #219, writer F9 and F1 (2026-11-09)

Repo `ai-news-collector`, worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/writer-f9-f1`, branch
`fix/018-writer-f9-f1` (one commit on origin/master). Read-only: no edits, commits, push, gh,
network or sub-agents.

Task and rules: `specs/018-daily-inference/records/prompt-writer-f9-f1-codex-2026-11-09.md`.
Executor report: `specs/018-daily-inference/records/report-writer-f9-f1-2026-11-09.md`.
Review `git diff origin/master...HEAD` and the docs `src/app/core/bulletin/writer.md`,
`builder.md`, `src/app/storage/bulletin_store.md`.

Check:
1. F9 as specified: which stories are removed, in every path (usable answer, invalid/unavailable
   answer, no stories); digest stories untouched; `dropped` ids; the day headline clearing. Can a
   non-English title still reach the stored payload, the preview page or `/` (e.g. through a gloss,
   the day headline after a model headline fails, `incident_story`, or a story whose language is
   stored in another form such as `German` or upper case)? Is removal by `s not in removed`
   (dataclass equality) safe when two stories compare equal?
2. Old stored payloads without `language` still load everywhere they are read (page, API, the next
   day's no-repeat keys in `bulletin_input.py`).
3. F1 prompt text and `WRITER_VERSION` bump; the writer journal replays identical bodies, so a
   rerun the same day costs one new call only because the version changed: confirm nothing else
   in the request body changed unintentionally.
4. Tests honest; doc Behavior matches code; test names real.

Run only: `env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_bulletin_writer_language.py tests/unit/test_bulletin_writer.py tests/unit/test_bulletin_builder.py`.

Final message: verdict (approve / changes needed), findings with file:line and a concrete
scenario, minor notes separately. Short.
