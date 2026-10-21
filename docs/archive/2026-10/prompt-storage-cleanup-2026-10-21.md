# Prompt: storage layer - shared helpers out of feature files, dead code, layout (2026-10-21)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first. Work in a separate git worktree from `origin/master`; other sessions may
work in the main folder. `venv1` is installed editable on the main folder: in the worktree run
checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/...` (adjust the relative path).

## Context

`src/app/storage/` has 20 modules. `repos.py` was split in PR #67; the rest was not looked at.
Found by the coordinator on 2026-10-21 (verify each against the code):

1. `storage/legacy_cleanup.py` (a one-off cleanup of legacy articles) is also the home of shared
   helpers: `encoded`, `fingerprint`, `private_write`, `_lock`, `_typed`. They are imported by
   daily signals (`core/daily/signals*.py`, `enrichment.py`), weekly (`core/weekly/frozen.py`),
   `storage/daily_signals_ledger.py`, `article_evidence_cache.py`, `cleanup_journal.py`,
   `reenrich_apply.py`, `reenrich_pilot_journal.py`, and scripts. Private names (`_lock`, `_typed`)
   are imported across modules.
2. `storage/reenrich_pilot_journal.py` (the re-enrichment pilot journal) is also the home of
   provider cost helpers: `PRICES`, `microdollars`, `is_overload`, imported by `core/jev.py`,
   `core/daily/signals.py`, `core/daily/enrichment.py`, `storage/daily_signals_ledger.py`,
   `core/weekly/frozen.py`, `cli/main.py`.
3. `storage/reenrich_apply.py` (220 lines) has no importer in `src/` or `scripts/`; only
   `tests/unit/test_reenrich_apply.py` and `docs/article-reenrichment.md` name it.

## Part 1: move shared helpers to modules named for what they do (one PR)

- Move the helpers of item 1 to one module named for their job (for example
  `storage/journal_files.py`: atomic private file writes, locks, canonical JSON and its
  fingerprint); make the cross-module ones public names (drop the leading underscore) and keep the
  code otherwise verbatim.
- Move the cost helpers of item 2 to a module named for provider cost (for example
  `core/provider_costs.py` or `storage/provider_costs.py`; choose by who uses them and say why).
  `PRICES` values and `microdollars` rounding must stay byte-identical: they decide paid budgets.
- Update every importer in `src/`, `tests/`, `scripts/`; no shims at the old names. Test monkeypatch
  strings that name these modules must still patch the module where the code looks the name up.
- `fingerprint` output is stored in journals and manifests: the function body must not change
  (add a test that pins the fingerprint of a fixed input before the move, if none exists).
- Weekly v2 files are only re-pointed to the new imports; nothing else there.

## Part 2: `reenrich_apply.py` (same PR, separate commit, or report)

Find out whether anything runs it: scripts, `cli/main.py`, operator docs
(`docs/article-reenrichment.md`, `docs/archive/` records of the re-enrichment runs), git history of
its last use. If it was a one-off whose run is finished and nothing calls it, delete it with its
test and doc row; otherwise keep it and say who runs it. Report the evidence either way.

## Part 3: layout and docs plan (no code; a file in the PR)

Write `docs/plan-storage-layout-2026-10-21.md`: should storage mirror `core/` (`storage/daily/`,
`storage/weekly/`, `storage/cleanup/`, ...) or stay flat; for each module its feature and the
feature doc that should cover it (`covers:` of `core/daily/signals.md`,
`core/ingestion/pipeline.md`, or a future doc); which features lack a code doc (re-enrichment,
legacy and non-news cleanup, article evidence cache) and whether they are still live features or
finished one-offs. Recommendation per item, no moves yet. Weekly v2: list only (deferred).

## Checks

- Full gate: `make lint PYTHON=...`, full `pytest` (same pass count as `origin/master`, minus
  removed tests if Part 2 deletes), `scripts/check_code_docs.py` and `--diff origin/master --strict`.
- Smoke: `ai-news --help`, the web app factory, `--help` of every changed script.

## Output

- One PR, do not merge. In your reply: the PR link; new module names and why; importers changed by
  area; the Part 2 verdict with evidence; the Part 3 summary as a table "module | feature | doc |
  recommendation"; exact checks with pass counts; open questions one line each (how settled, or a
  yes/no question for the owner with a recommendation, only if it changes what readers see or what
  is paid).
- Save any prompt you write for another session to a file per `AGENTS.md`.
