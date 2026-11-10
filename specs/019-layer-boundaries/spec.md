# Feature Specification: Layer boundaries (core does not import storage)

**Feature Branch**: `019-layer-boundaries`
**Created**: 2026-11-10
**Status**: Steps 1 and 2 done (2026-11-10); open: calculations out of repositories, the provider
journal loaded by name in two `core/` files, `ingest/` and `config/` (tasks T009-T015)
**Input**: Owner request of 2026-11-10: `core` and `storage` import each other; fix it by the book.

## The problem (measured 2026-11-10, master `a90a51e`)

- 25 of the files in `src/app/core/` import `app.storage`; 13 files in `src/app/storage/` import
  `app.core`. The packages form a cycle.
- `core/` holds two kinds of code: rules and calculations (no database needed) and use cases (code
  that opens sessions and calls repositories). Only the use cases need `storage/`.
- `storage -> core` is the right direction: a repository must know the type it stores. `core ->
  storage` is the wrong one.
- Three real faults:
  1. Helpers in the wrong place: `storage/journal_files.py` holds canonical JSON and its sha256
     fingerprint; four calculation modules import storage only for that, and
     `core/daily/provider_requests.py` and `storage/provider_journal.py` import each other.
  2. A repository runs a use case: `ArticleRepo.prune_older_than` calls
     `core.archive.capture.archive_articles` through a local import that exists to dodge the cycle.
  3. Repositories calculate: `storage/daily_signals.py` and `storage/period_signals.py` call
     `reconcile`; `storage/bulletin_input.py` calls `digest_title` and `cluster_key`.

## Target

Imports go one way: `cli/`, `web/` -> `usecases/` -> `storage/` -> `core/`.

No behavior change for readers, CLI flags, API responses, stored data or paid calls. Fingerprints
stored in journals and manifests stay byte-identical.

## User Scenarios & Testing

### User Story 1 - Rules are testable without a database (Priority: P1)

A developer changes a rule in `core/` and runs its tests; nothing from `storage/` is imported.

**Independent Test**: `tests/unit/test_layer_imports.py` passes with an empty list of `core/`
files that import `storage/`.

### User Story 2 - A repository only reads and writes (Priority: P2)

A repository returns rows or stored types; the use case calls the rule on them.

**Independent Test**: no module of `storage/` imports a function that computes (`reconcile`,
`digest_title`, `cluster_key`, `digest_summary`, `archive_articles`); types and version constants
are allowed.

### User Story 3 - The rule is kept by a check (Priority: P1)

A new import against the direction fails pytest.

**Independent Test**: adding `from app.storage...` to a `core/` module fails
`test_core_imports_storage_only_in_listed_files`.

### Edge Cases

- Imports inside functions count (the current dodge in `article_repo.py`).
- `monkeypatch` targets in tests name module paths; a moved module needs its targets moved
  (`tests/unit/test_monkeypatch_targets.py` catches a stale one).
- Code docs name modules in `module:` and `covers:`; a moved file needs its doc header, the three
  doc registries and the docstring link updated in the same PR.
- Scripts and deploy files that call modules by path (`python -m app...`) must be checked per move.

## Requirements

- **FR-001** `core/` imports nothing from `storage/` (after step 2: no exceptions).
- **FR-002** `storage/` imports nothing from `usecases/`.
- **FR-003** `storage/` calls no calculating function of `core/`; it may import types and constants.
- **FR-004** The rules FR-001..FR-003 are checked by pytest, and the exception lists only shrink.
- **FR-005** Each step is a pure move or a behavior-preserving split: the full suite passes
  unchanged except for import paths and monkeypatch targets.
- **FR-006** No interfaces (`Protocol`) per repository now. Decided 2026-11-10 (agent): one
  database, tests already run on SQLite, use cases work with ORM rows; a port is added only when a
  second implementation appears.

## Success Criteria

- **SC-001** The exception lists of `tests/unit/test_layer_imports.py` are empty.
- **SC-002** No `import-outside-toplevel` left that exists to dodge a `core`/`storage` cycle.
- **SC-003** Full gate green on every PR; production output of a nightly run is unchanged after the
  release that carries step 2.
