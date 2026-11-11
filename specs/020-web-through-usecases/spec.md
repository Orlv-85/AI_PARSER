# Feature Specification: Entry points go through use cases

**Feature Branch**: `020-web-through-usecases`
**Created**: 2026-11-11
**Status**: Draft (steps 1-3 approved by the owner 2026-11-11; step 4 is decided after them)
**Input**: Review remark of 2026-11-11: HTTP handlers parse JSON by hand, open sessions, commit and
call `create_all` inside the request (`src/app/web/routes/sources.py:79`); `web/` reads storage
directly in many files.

## The problem (measured 2026-11-11, master `cbbf994`)

- The rule in `src/app/README.md` ("Layers") says `cli/`, `web/` -> `usecases/` -> `storage/`, and
  code that opens sessions and calls repositories lives in `usecases/`. No test checks it for
  `web/` and `cli/`: `tests/unit/test_layer_imports.py` checks what `core`, `storage`, `ingest`,
  `usecases`, `config` and `observability` import, never what the entry points import. Besides
  `models_sql`, 12 files of `web/` and `cli/main.py` import `app.storage`; 5 files of `web/` call
  `commit()`.
- `create_all` runs inside most API handlers: 34 call sites in `web/` (21 `deps.create_all()`,
  13 `Base.metadata.create_all(bind=onboarding_engine)`). It dates from the first web commit
  (`e03a9ed`, 2026-02-21) with no recorded reason. It is still needed: production starts the new
  app before `alembic upgrade head` (`scripts/deploy_prod.sh`, "Starting app" then "Running
  migrations"), so in that window `create_all` creates new tables (the `page_views` migration
  is idempotent for that, `src/app/web/pages.md`); local runs (`scripts/run_web.sh`) do not migrate.
  What is not needed is running it again in every request.
- Three handlers read the body with `await request.json()` and check fields by hand
  (`routes/sources.py`: import, validate; `routes/pages.py`: `_login_response`). By the code, a
  body that is not JSON raises `JSONDecodeError`, and with auth on the login calls `.get` on any
  JSON value: both give 500 instead of a client error. Step 3 starts with tests that reproduce it.

## Target

- `cli/` and `web/` reach storage only through `usecases/`; a pytest check keeps the direction,
  with a list of files still in breach that only shrinks.
- Each table initializer (news storage, onboarding engine) runs until it succeeds once per app
  instance, not in every request.
- The three JSON bodies are read into Pydantic models inside the handler; a bad body gets a client
  error with the same `detail` strings as now.

No change for readers, CLI flags, stored data, paid calls or deploy defaults. API answers stay the
same for every request that gets a non-500 answer now, except what FR-005 lists.

## User Scenarios & Testing

### User Story 1 - The entry-point rule is kept by a check (Priority: P1)

A developer adds `from app.storage...` to a web route that is not on the list; pytest fails.

**Independent Test**: `tests/unit/test_layer_imports.py` fails when a `web/` or `cli/` file not on
the list imports any `app.storage` module other than `models_sql` (static or by literal
`import_module` / `__import__`), or a `web/` file not on the list calls `commit()`.

### User Story 2 - Requests do not touch the schema (Priority: P2)

After an initializer has succeeded, later requests of the same app do not run it again.

**Independent Test**: two requests to one app call each wrapped initializer once; a failing first
call answers 503 and the next request calls it again; two concurrent first requests run it once.

### User Story 3 - A bad body gets a client error (Priority: P2)

With auth on, the admin import, the validate call and the login answer a body that is not JSON, or
not an object, with a client error, never 500.

**Independent Test**: posting `not json` and `[]` to each of the three paths gives the stated code
and a string `detail`.

### Edge Cases

- Tests patch `app.web.app.create_all` / `SessionLocal` before `create_app()`; the wrappers are
  built inside `create_app`, so each test app starts fresh. The wrapped call stays inside the
  handlers' existing `try`, so storage errors still give 503.
- Sync handlers run in a thread pool: two first requests may race. Both initializers share one
  per-app lock (the two engines point at the same database; parallel DDL through two engines must
  not happen); each keeps its own success flag, set only after the DDL returns.
- A table dropped while the app runs is not recreated until restart (was: next request).
  `test_page_views_create_all_before_background` drops the table before the app is built;
  `test_page_views_failure_keeps_page` drops it mid-app with `create_all` stubbed: neither changes.
- The admin page shows `detail` only when it is a string (`static/admin/sources.js`): FastAPI's
  default list of validation errors must not reach these three paths.
- With auth off, login returns 200 before reading the body; that stays.
- `test_auth_middleware_coverage_is_pinned` posts an empty body to login and counts 401 as "blocked
  by the middleware"; today login answers 500 there. After FR-005 it answers 401, so the test must
  tell a credential 401 from a middleware 401 (for example by the `detail` string) and keep login
  in the public set.

## Requirements

- **FR-001** `cli/` and `web/` import from `app.storage` only the module `models_sql`; files that
  do more are listed in the test, and the list only shrinks. The scan reads static imports,
  `from app import storage`, wildcard imports and literal `import_module` / `__import__`.
- **FR-002** `web/app.py` is the composition root: it may import `SessionLocal` and `create_all`
  from `app.storage` to build `WebDeps`; no other exception is permanent.
- **FR-003** `web/` files that call `commit()` are listed in the test; the list only shrinks.
- **FR-004** `create_app` wraps both table initializers (news storage and onboarding engine): each
  runs until one call succeeds, then does nothing; one per-app lock serializes them; a failure
  propagates as now (503 from the handler).
- **FR-005** The import, validate and login bodies are read with Pydantic models inside the
  handler (decoded by stdlib json as before, then `model_validate`), with the current rules kept: `raw_text` is `str(value).strip()`
  and must be non-empty; ids accept ints and numeric strings, reject bools, `null` items and
  values below 1; `batch_id` is checked before `candidate_ids`; scope check last; login credentials
  are `str(value)`. Status codes and `detail` strings stay the same for every case that does not
  give 500 now. New: a body that is not JSON or not an object gets 422 with the path's "required"
  string (login with auth on: 401 "Invalid username or password"); a fractional id (`1.5`, also
  inside `candidate_ids`) gets 422 with the field's "integer" string (was: truncated).
- **FR-006** OpenAPI of the three operations does not change: no `requestBody`, no automatic 422
  response. A new test pins it (the route table test checks only route metadata).
- **FR-007** No `Protocol` per repository, no new dependency (same as spec 019, FR-006).

## Success Criteria

- **SC-001** After steps 1-3: the layer test lists the files still in breach; the bad-body tests
  pass; each initializer runs once per app after its first success.
- **SC-002** After step 4 (if approved): the lists of FR-001 and FR-003 are empty; only FR-002
  remains.
