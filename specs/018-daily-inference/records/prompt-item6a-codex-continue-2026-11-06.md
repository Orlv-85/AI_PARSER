# Prompt (Codex resume, gpt-6-astra high): spec 018 item 6a, finish the final checks (2026-11-06)

Your previous run hung after the full pytest suite passed (2326 passed, 2 skipped) and was stopped.
The code, tests, doc and render files are in place; do not redo them. Continue with the remaining
final checks of `prompt-item6a-codex-astra-2026-11-05.md`, once each, in this order:

1. `make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`
2. `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python scripts/check_code_docs.py` (if it has a CLI)
3. crapper, dryer 0.8 and mutator on `src/app/web/bulletin_view.py`, exactly as in that prompt.

After a fix rerun only the check that failed (and the bulletin tests); if you change code, rerun the
full pytest once at the end. Do not commit, push or use gh; no network; no sub-agents.

Then write the report `specs/018-daily-inference/records/report-item6a-bulletin-design-2026-11-05.md`
in the worktree with the fields of that prompt (owner's answer on the look: "pending, coordinator
asks after render"; render script and output files under `/private/tmp/item6a-render/`). Final
message: report path, changed files, check results with counts, open questions. English.
