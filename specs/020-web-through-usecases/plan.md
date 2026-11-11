# Implementation Plan: Entry points go through use cases

**Branch**: per step, see below | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)
**Input**: `spec.md`; counts taken from master `cbbf994` with grep; draft reviewed by Astra
(`records/review-spec-astra-2026-11-11.md`)

## Summary

Add the missing check for `web/` and `cli/`, stop creating tables in every request, read JSON
bodies through Pydantic models, then (step 4, after an owner go) move session work out of the
handlers into `usecases/`. Each step is its own PR.

## Technical Context

**Language/Version**: Python 3.14 | **Testing**: pytest; the import scan of
`tests/unit/test_layer_imports.py` (stdlib `ast`); Pydantic v2 (already a dependency)
**Constraints**: no change to readers, CLI, stored data, paid calls, deploy defaults; API answers
change only as FR-005 says
**Where the rules live**: `src/app/README.md` ("Layers"), `src/app/web/pages.md`,
`src/app/usecases/sources/onboarding.md`

## Steps

| Step | What | Size | Risk |
| --- | --- | --- | --- |
| 1 | Rule text for entry points in `src/app/README.md`; name-aware scan in `test_layer_imports.py`; `STORAGE_IN_ENTRY_POINTS` (12 files: 11 of `web/`, `cli/main.py`) and `COMMITS_IN_WEB` (5 files), each asserted equal to what the scan finds | small | none: test only |
| 2 | `create_app` wraps both initializers (FR-004); `routes/sources.py` calls the onboarding wrapper from `WebDeps` instead of `Base.metadata.create_all` | small | concurrency; see spec edge cases |
| 3 | Pydantic models for the import, validate and login bodies (FR-005, FR-006); the two `_parse_source_onboarding_*` helpers become model validators; tests first | small | coercion and error order; pinned by tests |
| 4 | One PR per file group: session and commit code of the handlers moves to `usecases/` (start: `routes/sources.py`, `source_intake.py`, `source_onboarding.py`); each PR removes its files from the two lists | medium each | same checklist as spec 019 step 2: doc headers, registries, docstring links, monkeypatch targets (`test_monkeypatch_targets.py`) |

Order: 1, 2, 3, then the owner decides on 4. Step 1 first so steps 2-4 can only shrink the lists.

## Step 1 detail: the scan

- `imports_package` answers yes/no per package; the new check needs the module names. Add a
  helper that returns the `app.storage...` modules a file imports (static `import` /
  `from ... import`, `from app import storage` counts as the package itself, wildcard imports,
  literal `import_module` / `__import__` through `_loaded_by_name`) and, for `web/app.py`, the
  imported names. Tests of the helper: mixed import, alias, import inside a function,
  `from app import storage`, wildcard, `import_module("app.storage.x")`.
- A file is in `STORAGE_IN_ENTRY_POINTS` when it imports any `app.storage` module other than
  `app.storage.models_sql`. `web/app.py` may import exactly `SessionLocal` and `create_all` from
  `app.storage` (FR-002) and is not listed.
- `COMMITS_IN_WEB`: `web/` files with a call `<x>.commit()` (AST `Call` on attribute `commit`).
- `cli/main.py` is listed; `cli/` has no commit list in this spec (decided 2026-11-11 (agent): the
  CLI is one file, it is moved in step 4 if approved, a second list adds nothing until then).

## Step 2 detail

- In `web/app.py`: one `threading.Lock` per app; `_once(create, lock)` returns a callable that
  takes the lock, returns if its own flag is set, calls `create`, sets the flag after it returns.
  `deps.create_all` and the new `WebDeps.create_onboarding_tables` are two such callables sharing
  the lock. `routes/sources.py` stops importing `Base`; every call stays inside the handlers'
  existing `try`.
- Tests: two sequential requests call each initializer once; a raising first call gives 503 and
  the second request calls again; two threads on a fresh app run each initializer once; a second
  app instance calls again.
- Docs: `pages.md` says "once per app instance" where it says "retain `deps.create_all()`";
  `onboarding.md` gets the rule for the onboarding tables (it has no such passage now); `web/app.py`
  has no code doc and is not added to `pages.md` `covers:` (decided 2026-11-11 (agent): it holds
  the auth middleware and the wiring of every area; covering it from the pages doc would force
  page-doc edits for unrelated changes); the `_once` docstring names `pages.md`.

## Step 3 detail

- Models in `web/models.py`: `SourceOnboardingImportRequest`, `SourceOnboardingValidateRequest`,
  `LoginRequest`. Fields default to `None`; `mode="before"` field validators hold today's rules
  (FR-005) and raise `PydanticCustomError` with the exact current string; a `model_validator`
  (`mode="after"`) does the scope check ("batch_id or candidate_ids is required"). Fields are
  declared in today's check order, so the first error is today's error.
- Handler: `Model.model_validate(json_body(await request.body()))`: `json_body` decodes with
  stdlib `json.loads` like `request.json()` (BOM, UTF-16/32, last duplicate key, lone
  surrogates; `model_validate_json` rejects these, Astra review); on `ValidationError` it raises
  `HTTPException(422, errors()[0]["msg"])`; a JSON or type error of the whole body maps to the
  path's "required" string. Login keeps the early 200 when auth is off and parses inside
  `_login_response` (`test_page_router_handlers_only_delegate`).
- Tests first: `not json`, `[]`, `{}` on the three paths; `1.5` as `batch_id` and in
  `candidate_ids`; numeric string ids still accepted; bool, `null` item, `0` keep their strings;
  error precedence (`batch_id` bad and `candidate_ids` bad -> `batch_id` string); malformed body
  with auth off -> 200; OpenAPI of the three operations (FR-006). Adjust
  `test_auth_middleware_coverage_is_pinned` (spec edge cases). Pinned tests that must stay green:
  `test_source_onboarding_import_route_rejects_non_mapping_and_blank_text`,
  `test_source_onboarding_validate_route_rejects_invalid_payload_shapes`,
  `test_source_onboarding_validate_rejects_invalid_identifier_payloads`,
  `test_source_onboarding_validate_route_accepts_candidate_ids_only`,
  `test_login_api_returns_ok_when_auth_disabled`, `test_extracted_login_preserves_credentials_and_json`,
  `test_login_fail_returns_generic_error`, `test_login_success_sets_cookie_and_grants_access`.

## Decisions

- Once per app, not at startup: decided 2026-11-11 (agent): startup would need a retry when the
  database is down (now: 503 per request) and tests build apps without running the lifespan; the
  once-wrapper keeps both behaviors and removes the per-request cost.
- `create_all` stays: production starts the app before migrating, and local runs do not migrate.
- Model inside the handler, not a typed body parameter: keeps string `detail` for the admin page
  and OpenAPI unchanged.
- Malformed login body (auth on) is 401, not 422: decided 2026-11-11 (agent): the login form
  always sends both fields; one failure answer for login reveals nothing new.
- Fractional ids are rejected: decided 2026-11-11 (agent): `1.5` is not an id; truncating it to 1
  could validate the wrong candidate.
- Two engines (`SessionLocal` and `onboarding_engine`) to one database stay: no reason recorded;
  looked at again in step 4 when the onboarding handlers move.

## Complexity Tracking

None: one small wrapper, three models.
