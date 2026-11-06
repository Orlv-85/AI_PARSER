# Prompt (Codex executor gpt-6-astra, high): spec 018 item 6a, bulletin page design (2026-11-05)

Your task is the design prompt
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/specs/018-daily-inference/records/prompt-item6a-bulletin-design-2026-11-05.md`.
Read it fully and do it, with these changes for a Codex run (they win over that prompt):

- The worktree already exists: your current directory, branch `feat/018-item6a-bulletin-design`
  from `origin/master`. Do not run `git worktree`, `git fetch`, commit, push or any `gh` command.
  No network. Main folder (read only): `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`.
- Python and tools: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`,
  `.../.venv/bin/pytest`, `.../.venv/bin/ruff`. Set `PYTHONDONTWRITEBYTECODE=1`.
- Do steps 1, 2, 3 and 5 of that prompt. **Skip step 4** (running the app, screenshots, Artifact,
  question to the owner): the coordinator does it after you. Instead, for step 4 write a small
  script `/private/tmp/item6a-render/render.py` (outside git; if you cannot write there, put it under
  `.metrics/item6a-render/`, git-ignored) that loads the three sample days from
  `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/fr022/bulletins-2026-11-02..04.json`
  (key `<date>.stored`) into a scratch SQLite DB through `BulletinRepo` and renders through the
  FastAPI `TestClient` the pages `/bulletin?date=2026-11-04`, a skipped day (store one as
  `skipped` if none is skipped), a missing day and the empty store, writing each as an `.html` file
  next to the script with `bulletin.css` inlined or copied beside it so a browser can open the files
  directly. Run it once and list the output files in your report. Never copy the sample data into git.
- While working run only the bulletin tests (`rg -l "bulletin_page" tests` plus the new ones) and
  ruff on changed files. At the end, once each, in this order:
  1. `PYTHONDONTWRITEBYTECODE=1 /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest`
  2. `make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`
  3. `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python scripts/check_code_docs.py` (if it has a CLI)
  4. ub-mode tools, from the worktree root, with
     `E="env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1"`:
     - `$E ~/tools/unclebob/crapper/crapper src/app/web/bulletin_view.py` (CRAP under 10)
     - `~/tools/unclebob/dryer/dryer --threshold 0.8 src/app/web/bulletin_view.py`
     - `$E ~/tools/unclebob/mutator/mutator --use-existing-coverage --test-command "/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= <bulletin test files>" src/app/web/bulletin_view.py`
       (kill survivors with tests or give a reason per survivor).
  After a fix rerun only the check that failed. Do not study the tools' sources.
- Do not spawn a doc review or any sub-agent: a separate review covers the doc.
- Report: write `specs/018-daily-inference/records/report-item6a-bulletin-design-2026-11-05.md` in
  the worktree with the fields of that prompt, but "owner's answer on the look" reads "pending,
  coordinator asks after render"; add the render script path and output files. Your final message:
  the report path, the changed files, the check results (pass/fail with counts), open questions.
  English, no Russian message to the owner.
