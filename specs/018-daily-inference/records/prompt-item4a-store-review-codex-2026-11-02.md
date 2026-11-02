# Prompt (Codex review, gpt-6-astra high): spec 018 item 4a, bulletin storage and API (2026-11-02)

Read-only review. Directory (git worktree of branch `feat/018-item4a-bulletin-store`, changes
uncommitted; compare with `origin/master`, include untracked files):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4a-store`.
Do not edit files, commit, push or use gh. No network, no paid calls.

The executor's prompt: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/prompt-018-item4a-store-codex-2026-11-02.md`
(read it: scope, decisions already made, test names). Spec: `specs/018-daily-inference/spec.md`
FR-007, FR-008.

## Check

1. `git diff origin/master` plus every untracked file, read in full.
2. Correctness with concrete inputs:
   - Upsert: SQLite and PostgreSQL both (`on_conflict_do_update ... where ... returning`): is a
     posted row (telegram_message_id set) never replaced on either? Does `returning` give None when
     the WHERE blocks the update on both dialects? Is `replaced` logged right? Session state after
     a refused save (stale objects, `populate_existing`)?
   - CLI: `--dry-run` stores nothing; skipped and ready days stored; `--write` stores the written
     bulletin and its numbers; a writer failure path; `create_all()` in the CLI: any risk for the
     production PostgreSQL schema managed by Alembic (table created outside Alembic, then the
     migration's "create only when missing")?
   - Migration: revision chain correct (single head), create-only-when-missing, downgrade, column
     types on PostgreSQL (JSON vs JSONB, timezone-aware timestamp, bigint).
   - API: public path registered exactly; 400/404/503; `date` absent -> latest ready; response
     JSON types (date and datetime serialization); no `telegram_message_id` leak; existing APIs and
     route table unchanged except the new route.
   - FR-007 payload: "stories with texts, areas, links, outlets, article ids, origin". The payload is
     `Bulletin.as_dict()`; `Story` has no article ids. Say what is missing and the smallest fix.
3. Docs: `src/app/storage/bulletin_store.md` rules match code; every rule names existing tests that
   check it; registrations in README files; builder.md/writer.md edits accurate.
4. Tests: would each fail if its code were reverted? Hand mutations (drop the WHERE, store on
   dry-run, wrong latest ordering, leak telegram id, skip public-path registration) and which tests
   kill them; name survivors.
5. Run: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" tests/unit/test_bulletin_store.py tests/unit/test_bulletin_builder.py tests/unit/test_web_route_table.py | tail -1`

## Report (your final message)

Findings ranked most severe first: file:line, problem, concrete failing input, one-line fix. Then
mutation results. Then "clean" if nothing must change before merge. Be brief.
