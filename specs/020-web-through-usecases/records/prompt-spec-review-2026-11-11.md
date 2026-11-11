# Review: spec 020 draft (entry points go through use cases)

You review a feature spec before any code is written. Read-only: do not edit files, do not commit,
no network, do not spawn sub-agents. Run no tests unless a claim needs one; then only the named
test file with `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= <file>`.

## Read

1. `AGENTS.md` (rules for specs, feature docs, owner questions).
2. `specs/020-web-through-usecases/spec.md`, `plan.md`, `tasks.md` (the draft).
3. `specs/019-layer-boundaries/spec.md`, `plan.md` (the method this spec repeats).
4. `src/app/README.md`, section "Layers"; `tests/unit/test_layer_imports.py`.
5. The code the spec names: `src/app/web/app.py`, `src/app/web/routes/__init__.py`,
   `src/app/web/routes/sources.py`, `src/app/web/routes/pages.py` (login), `src/app/web/models.py`,
   `src/app/web/static/admin/sources.js`, `scripts/run_web.sh`, `scripts/deploy_prod.sh`
   (migrations), `src/app/web/pages.md`, `src/app/usecases/sources/onboarding.md`.

## Check

1. Facts: every count and claim in "The problem" (files importing `app.storage` beyond
   `models_sql`, files calling `commit()`, number of `create_all` calls, the 500 cases, when
   `create_all` appeared, what production and local runs do). Give the command you used.
2. Behavior: does any step change what readers see, CLI flags, stored data, paid calls or deploy
   defaults beyond what FR-005 lists? Does the once-wrapper (FR-004) keep 503 on storage errors
   and table creation for a new local database? Any race or test pattern it breaks (tests that
   patch `app.web.app.create_all` / `SessionLocal`, tests that drop tables)?
3. FR-005: can the stated `detail` strings and OpenAPI stay unchanged with
   `Model.model_validate_json` inside the handler? Name every pinned test that could break. Is
   the bool rejection of ids kept by Pydantic v2 as planned?
4. Step 1 test design: is the rule (only `app.storage.models_sql`; `web/app.py` allowed
   `SessionLocal`, `create_all`; commit list) checkable with the existing scan helpers, and does it
   catch `import_module("app.storage...")` like the 019 checks do?
5. Gaps: anything the plan misses (docs to update, registries, monkeypatch targets, the second
   engine) or decisions that should be questions to the owner (only product or money questions).

## Report

Short markdown: a list of findings, each with severity (blocker / should fix / note), the file and
line, what is wrong and the fix. Then "facts checked" with commands and results. No praise, no
restating the spec.
