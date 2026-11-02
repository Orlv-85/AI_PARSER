# Prompt (Codex review, gpt-6-astra high): spec 018 item 4c, bulletin preview page (2026-11-02)

Read-only review. Directory (git worktree of branch `feat/018-item4c-preview-page`, changes
uncommitted; compare with `origin/master`, include untracked files):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page`.
Do not edit files, commit, push or use gh. No network, no paid calls. Do not spawn a sub-agent.

The executor's prompt: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/prompt-018-item4c-preview-page-codex-2026-11-02.md`
(read it: scope and decisions already made). Spec: `specs/018-daily-inference/spec.md` FR-019.

## Check

1. `git diff origin/master` plus every untracked file, read in full.
2. Correctness with concrete inputs (`src/app/web/bulletin_view.py`, route in
   `src/app/web/routes/pages.py`):
   - Payload keys used by the view (`key_results`, `rubric_story`, `cooperation`,
     `incident_story`, `day_number`, story `links[].outlet/url`, `site_note`, `gloss`, `headline`,
     `text_origin`, `origin`, `area`, `title`) against `Bulletin.as_dict()` / `Story` in
     `src/app/core/bulletin/builder.py` and the writer. Is every story of a ready bulletin shown, in
     stored order? Any key that can be missing in a real stored row (title-only day, world story,
     older row) and give a 500?
   - Statuses: no date + no ready row; date of a skipped row; missing row; bad date (is the 400 an
     HTML page or JSON, and does that matter); `SQLAlchemyError` -> 503; any other exception path.
   - `_parse_day` is a private name imported from `routes/bulletin.py`: rename to a public helper or
     keep?
   - `deps.create_all()` on every page request: same as the other page routes?
   - Navigation: next link stops at yesterday UTC; date in the past far.
3. Security: every stored value escaped, attributes quoted; only http/https links; `javascript:`,
   `data:`, `//host`, leading spaces, mixed case; any unescaped interpolation (reason, numbers,
   day). Public path added exactly once; auth middleware still protects everything else.
4. Not linked: no other page, template, view or static file links `/bulletin`; `/` and the other
   pages unchanged; route table test pinned correctly.
5. CRAP: the executor reports `build_pages_router` 25.2 and `create_app` 25.0. Compare with
   `origin/master` (run crapper on master's files in a temp copy if needed, or reason from the
   diff): did this change raise them? If the new route body adds branches inside
   `build_pages_router`, say the smallest move that keeps it out (a module-level helper).
6. Docs: `src/app/web/pages.md` rules match code; every rule names existing tests; covers list;
   `pyproject.toml` package data.
7. Tests: would each fail if its code were reverted? Hand mutations (drop escape on headline, allow
   any scheme, show next link for today, remove `/bulletin` from public paths, 200 for missing
   row, skip `rubric_story`) and which tests kill them; name survivors.
8. Run: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" tests/unit/test_web_bulletin_page.py tests/unit/test_web_route_table.py tests/unit/test_bulletin_store.py | tail -1`

## Report (your final message)

Findings ranked most severe first: file:line, problem, concrete failing input, one-line fix. Then
mutation results. Then "clean" if nothing must change before merge. Be brief.
