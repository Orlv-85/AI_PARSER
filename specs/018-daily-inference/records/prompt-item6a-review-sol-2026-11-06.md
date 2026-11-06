# Prompt (Codex review, gpt-6.1-sol high, read-only): spec 018 item 6a (2026-11-06)

You review PR #214 in the current worktree (branch `feat/018-item6a-bulletin-design`, one commit
on `origin/master`; see `git diff origin/master...HEAD`). Read only; do not edit files, commit,
push or use gh; no network; no sub-agents.

Task given to the executor: `specs/018-daily-inference/records/prompt-item6a-bulletin-design-2026-11-05.md`
(as changed by `prompt-item6a-codex-astra-2026-11-05.md`). Report:
`specs/018-daily-inference/records/report-item6a-bulletin-design-2026-11-05.md`.

Check, with file:line for every finding:
1. Correctness of `src/app/web/bulletin_view.py` against the payload shape in
   `src/app/storage/bulletin_store.md` and `src/app/core/bulletin/` (missing or None fields:
   `headline`, `rubric_name` with and without `rubric_story`, `incidents` 0 with/without
   `incident_story`, `headline_cut`, `reaction`, empty `links`); escaping of every stored value;
   http/https-only links still hold.
2. Issue order and section names match `specs/018-daily-inference/voice.md` "Structure of an
   issue"; empty sections left out; story shows headline else title, site notes, gloss, area,
   outlets.
3. Nothing changed outside 6a scope: routes, URLs, switches, storage, `digest.css`, other pages.
4. `src/app/web/pages.md`: each Behavior rule names tests that really check it; Decisions are
   short and correct; Code map row for `bulletin.css`. Flag rules a test does not check.
5. Tests in `tests/unit/test_web_bulletin_page.py`: do the new tests check the rule (not just a
   substring that passes anyway)? Missing regression cases?
6. `src/app/web/static/css/bulletin.css`: obvious phone overflow risks (fixed widths, long URLs,
   `pre` in the checking block), contrast of dark palette, focus states.

Run only: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= -p no:cacheprovider tests/unit/test_web_bulletin_page.py tests/unit/test_web_static_assets.py`

Output: findings ranked by severity (blocker / should fix / nit), each with file:line, the
failure scenario and a suggested fix; then "no findings" areas; then the test result line.
English.
