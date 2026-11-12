# Review 2: typed payloads - defensive reads and TypedDict fields (2026-11-12)

Read-only review. Do not edit files, commit, push or use the network. Do not spawn sub-agents.

Branch `refactor/typed-signal-models`, one commit on top of `origin/master`:
`git diff origin/master...HEAD`. A first review found nothing; this one goes deep on two points
only. Read the old code with `git show origin/master:<path>` next to the new code.

## 1. Reads of stored or untrusted data

Stored JSON is read back from the database: daily snapshots (old methodology versions included)
by `storage/period_signals.py`, `core/periodic/period_compute.py`, `core/daily/signals_brief.py`,
`core/periodic/period_brief.py`; model answers by `parse_brief`, `parse_period_brief`,
`core/bulletin/writer.py` (`parse_writer`, `_answer_shaped`, `_evidence`, `_story_text`).

For every place in the diff where such data is read, compare old and new code for these inputs:
missing key, value `None`, wrong type (list instead of dict, str instead of int), non-dict list
entry, empty list. Report any input where the new code raises, or returns a different value, while
the old code did not. Pay attention to `.get(...)` turned into `[...]`, `or {}` / `or []` removed,
`isinstance` checks removed or narrowed, and changed defaults.

## 2. TypedDict fields vs values actually written

For every field of `src/app/core/daily/signals_payload.py`, `src/app/core/periodic/period_payload.py`
and the TypedDicts in `signals_brief.py` / `writer.py`, find the code that writes it and check the
declared type: can the value be `None`, a float where `int` is declared, absent where the field is
required (or always present where it is `NotRequired`)? Old stored payloads count: a field that
older methodology versions did not write must not be read as required without a default.

## Check

Run only: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -p no:cacheprovider tests/unit/test_daily_signals_compute.py tests/unit/test_daily_signals_brief.py tests/unit/test_period_compute.py tests/unit/test_period_month.py tests/unit/test_period_brief_flow.py tests/unit/test_bulletin_writer.py`

## Report

1. Findings ranked by severity: file:line, the input, old result, new result.
2. Evidence of coverage even when there are no findings: one line per read site checked
   (file:line, verdict), and one line per TypedDict listing any field you doubted and why it is fine.
Keep it short otherwise.
