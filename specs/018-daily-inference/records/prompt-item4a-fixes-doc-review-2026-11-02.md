# Item 4a review fixes: feature document review

Work only in this item4a-store worktree; read-only, no network, paid calls, commits, push or gh.
Read the fixes prompt at
/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/prompt-018-item4a-store-fixes-codex-2026-11-02.md.
Review the new edits to builder.md and bulletin_store.md against code and tests: article ids in
member order with None omitted, stale identity refreshed after refusal, removal of replaced log
field, storage failure 503 coverage, and isolated PostgreSQL migration/upsert test.
Report concrete discrepancies to the parent; do not edit files or run tests.
This is the separate-session feature document review required by AGENTS.md.

Handoff rule: save prompts before sharing them; feature prompts and reports belong under
specs/<NNN>-<name>/records/, never the docs/ root. Do not overwrite earlier prompts or reviews.
