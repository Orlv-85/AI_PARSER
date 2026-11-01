# Prompt: re-review of PR #190 fix commits 34524f3 and a343dcd (018 W6) (2026-11-01)

Same rules as `prompt-item5-w6-review-2026-11-01.md` (read-only, own worktree named with `pr190`,
no main-folder changes, no paid calls, no network). Review only commits `34524f3` and `a343dcd` on
`feat/018-world-w6-text` against your first review and the fixes prompt
`prompt-item5-w6-fixes-2026-11-01.md` (coordinator records folder:
`/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/coord-records/specs/018-daily-inference/records/`;
the implementer's fixes summary is at the end of `report-item5-w6-2026-11-01.md` there).

1. Must-fix 1: no path left where the world stream rewrites a real document (including a real
   `pending` document it downloads: does the download step itself change its metadata?).
2. Must-fix 2: the marker is set after `archive_articles` creates the document, in a second step.
   Is it in the same transaction? If the run crashes between the two, does an unmarked world
   document reach the nightly coverage and retries? Other readers of `source_key` (`archive purge
   --source`, retention, metrics, any `GROUP BY source_key`, web or API views of archive sources):
   does the value `world` break or show anything? Nightly path still unchanged.
3. Fallback: `failed`/`gave_up` -> `no_text`; only `pending` downloaded; next outlet next run.
4. Mutations: your earlier survivor M14 plus at least 5 new ones on the fix (marker missing on one
   path, exclusion in only one of `window_states`/`due`, takeover by a real article, read-only
   existing document); table killed/survived.
5. Scoped pytest on the world and archive test files, ruff,
   `scripts/check_code_docs.py --diff origin/master --strict` (exit code).

Report: verdict (merge / merge after fixes), must fix vs nice to have, mutation table, checks.
