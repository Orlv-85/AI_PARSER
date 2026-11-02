# Prompt (Codex, gpt-6.1-sol high): ub-mode pass 1, provider journal (2026-11-02)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch
`refactor/ub-provider-journal`, checked out from origin/master):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/ub-provider-journal`. Do not touch
any other directory. Do not run git commit, push or any gh command. No network, no paid calls (tests
use fakes; never call Jev or DeepSeek). Do not spawn a doc review or any sub-agent: a separate
reviewer (another model) reviews the code and the doc after you.

Speed rule: while working run only the journal's tests (list below) and `ruff` on changed files; at
the end run the full suite, `make lint`, crapper, dryer and mutator once each, in that order; after a
fix rerun only the check that failed.

## Scope

Whole-repo ub-mode pass (owner yes 2026-11-02), module by module, money paths first. This is
module 1: `src/app/storage/provider_journal.py` (`PilotJournal`), the durable payment journal every
paid Jev and DeepSeek call goes through (reservations, caps, replay, failed-call blocks). It has no
feature doc yet.

Measured on master (crapper, full suite coverage):

| Function | CC | Cov | CRAP |
| --- | --- | --- | --- |
| `PilotJournal.call` | 21 | 90.9% | 21.3 |
| `PilotJournal._attempt` | 14 | 71.4% | 18.6 |
| `PilotJournal.review_transport_failure` | 8 | 50.0% | 16.0 |
| `PilotJournal.restore_valid_summary` | 7 | 50.0% | 13.1 |

Goal: every function of the module under CRAP 10, behavior exactly unchanged. This is a pure
refactor plus tests: no change of any guard, cap, key, SQL, file layout, exception type or message,
log event or field, return value, or call order (reservation before dispatch, commit after usage).

## Steps (doc first, then tests, then code)

1. Read `AGENTS.md` (sections "Feature Docs Next To Code", "Code Changes"), the module, its callers
   (`rg -n "PilotJournal|provider_journal" src`), and its tests:
   `tests/unit/test_provider_requests.py tests/unit/test_world_change.py tests/unit/test_world_screen.py
   tests/unit/test_bulletin_writer.py tests/unit/test_daily_enrichment.py tests/unit/test_daily_publish_day.py
   tests/unit/test_semantic_admission_pipeline.py tests/unit/test_world_report.py`.
2. Feature doc `src/app/storage/provider_journal.md` (header `<!-- code-doc` / `module:
   src/app/storage/provider_journal.py` / `covers:` / `  - src/app/storage/provider_journal.py` /
   `-->`; module docstring names it): Behavior of what the journal guarantees now (reserve, cap
   check, dispatch, usage pricing, commit, replay of an identical body, failure states and the review
   that unblocks them, transient release, truncated-summary review, report), a Mermaid flow of
   `call`, each rule naming the tests that check it (a rule without a test says so), Decisions (only
   ones a source states; otherwise "decided 2026-11-02 (agent): <reason>" and list it in your
   report), Invariants, Code map, Tests. Register it in `docs/README.md`, `README.md`,
   `src/app/README.md` like the other code docs. Describe what the code does; do not change behavior
   to match a doc.
3. Tests for the uncovered branches first (the lines crapper/coverage show as missed in `_attempt`,
   `review_transport_failure`, `restore_valid_summary`, `call`), in `tests/unit/test_provider_requests.py`
   or a new `tests/unit/test_provider_journal.py`. They pass on the current code (characterization);
   name them in the doc.
4. Refactor: extract small named helpers (one decision each), keep public method signatures. No new
   abstractions beyond what removes branches. Functions under complexity 10 and CRAP 10.
5. Final checks (once each, in this order; report last lines and exit codes):
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" -n auto | tail -1`
   - `PYTHONPATH=src make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python 2>&1 | tail -5`
   - `env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 ~/tools/unclebob/crapper/crapper src/app/storage/provider_journal.py`
     (report every function of the module with CC, coverage, CRAP)
   - `~/tools/unclebob/dryer/dryer --threshold 0.8 src/app/storage/provider_journal.py src/app/core/daily/provider_requests.py`
     (report pairs)
   - `env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 ~/tools/unclebob/mutator/mutator --use-existing-coverage --test-command "/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_provider_requests.py <your new test file if any> tests/unit/test_world_change.py tests/unit/test_bulletin_writer.py tests/unit/test_daily_enrichment.py" src/app/storage/provider_journal.py`
     (kill survivors with tests or give a one-line reason each)
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python scripts/check_code_docs.py --diff origin/master --strict; echo exit=$?` (alone, last)

## Report (your final message)

Files changed, one line each; the new tests and which branch each covers; outputs of step 5 (crapper
table before/after); mutator sites, killed, survived, uncovered and what you did with survivors;
every "decided (agent)" line of the doc; anything you could not do, one line each.
