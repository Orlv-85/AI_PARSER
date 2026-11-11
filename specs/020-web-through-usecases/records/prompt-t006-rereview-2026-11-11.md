# Re-review: spec 020, phase 3 (T006-T008), after fixes

Read-only. Do not edit, commit or use the network; no sub-agents. The branch has one WIP commit
plus uncommitted fixes; review `git diff origin/master` as a whole. Run only:
`PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_web_source_onboarding_api.py tests/unit/test_auth_stage1.py tests/unit/test_web_route_table.py tests/unit/test_code_docs.py`

Your first review is in
`/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/ad1fe9ff-b650-48b7-8a5e-ee3a1a7dd365/scratchpad/review-t006-1.md`
(findings 1-4). The fix: bodies are decoded by `json_body` (stdlib `json.loads`, as Starlette's
`request.json()`; `RecursionError` becomes `ValueError`), then `Model.model_validate(...)` (python
mode) instead of `model_validate_json`. Docs updated for the left-to-right `candidate_ids` order.

Check only:
1. Each finding 1-3 is fixed: compare old (`git show origin/master:src/app/web/routes/sources.py`,
   `.../pages.py`) and new behavior again for BOM, UTF-16/32, duplicate keys, lone surrogates
   (ignored, overwritten, in `batch_id`), deep nesting (250 and 10**6 levels), mixed
   `candidate_ids` errors. List any remaining difference beyond FR-005's stated changes.
2. Python-mode validation: any value that `request.json()` can produce for which the models now
   answer differently from the old hand checks (for example `raw_text` as a dict, list or number;
   credentials as numbers or `null`).
3. New tests prove the fixes (would they fail with `model_validate_json`?).

Report: findings with severity, file:line, fix; or "no findings". No praise.
