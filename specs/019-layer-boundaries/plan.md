# Implementation Plan: Layer boundaries

**Branch**: per step, see below | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)
**Input**: `spec.md`; import lists taken from master `a90a51e` with grep

## Summary

Split what is now `core/` into rules (`core/`) and use cases (`usecases/`), move calculations out of
repositories, and keep the direction with a pytest check. Four steps, each its own PR (step 3 is
several). No behavior change.

## Technical Context

**Language/Version**: Python 3.14 | **Testing**: pytest, `ast` for the import check (stdlib only)
**Constraints**: no change to CLI, API, stored data, paid calls, deploy defaults; fingerprints
byte-identical (`test_fingerprint_of_fixed_input_is_pinned`)
**Where the rule lives**: `src/app/README.md`, section "Layers"

## Steps

| Step | What | Size | Risk |
| --- | --- | --- | --- |
| 1 | `encoded`, `fingerprint`, `serialize` move to `core/canonical_json.py`; `storage/journal_files.py` keeps the private file writes; the check `tests/unit/test_layer_imports.py` starts with the list of use cases still in `core/` | small | none: pure move |
| 2 | Use cases move from `core/` to `src/app/usecases/` (same sub-package names); `USE_CASES_IN_CORE` becomes empty | about 21 files plus tests, docs, monkeypatch targets | conflicts with any open branch; do it when no PR is open |
| 3 | Calculations leave repositories, one repository per PR: `prune_older_than` (archive then delete, use case owns the order and the transaction), `daily_signals.py`, `period_signals.py`, `bulletin_input.py` | medium each | behavior: each PR starts with tests that pin the current output |
| 4 | Storage-side check: `storage/` does not import `usecases/` and calls no calculating function of `core/` | small | none |

Order: 1, 2, 4 (the `usecases` half), 3, 4 (the calculation half). Step 2 before step 3 because
step 3 needs a place for the code that leaves the repositories.

## Step 2 detail: what moves

Files of `USE_CASES_IN_CORE` in `tests/unit/test_layer_imports.py`. Before the move, each file is
read: a file that mixes a rule and a use case is split, the rule stays in `core/`. Known mixed
files: `core/daily/enrichment.py` (`digest_title` is a rule used by storage),
`core/daily/signals.py`, `core/archive/capture.py`.

## Decisions

- Three layers, no ports: see FR-006.
- Package name `usecases`: decided 2026-11-10 (agent); owner informed, no objection.
- A ratchet list in a test instead of `import-linter`: decided 2026-11-10 (agent): no new
  dependency, same style as `scripts/check_code_docs.py`, and it can list exceptions that shrink.
- `journal_files.py` keeps its name and place: it writes files, which is storage work.

## Complexity Tracking

None: no new abstraction is added.
