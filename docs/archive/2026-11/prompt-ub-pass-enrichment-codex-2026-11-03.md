# Prompt (Codex, gpt-6.1-sol high): ub-mode pass 3, daily enrichment (2026-11-03)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch
`refactor/ub-enrichment`, checked out from origin/master):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/ub-enrichment`. Do not touch any
other directory. Do not run git commit, push or any gh command. No network, no paid calls (tests
use fakes; never call Jev or DeepSeek). Do not spawn a doc review or any sub-agent: a separate
reviewer (another model) reviews the code and the doc after you.

Speed rule: while working run only the feature tests (list below) and `ruff` on changed files; at
the end run the full suite, `make lint`, crapper, dryer and mutator once each, in that order; after a
fix rerun only the check that failed. Run the full suite again after the last test you add (a
previous executor skipped this and missed a failure of `tests/unit/test_monkeypatch_targets.py`).

## Scope

Whole-repo ub-mode pass, module 3 and the last one (owner 2026-11-03): the daily digest enrichment,
paid Jev and DeepSeek calls every night. Doc: `src/app/core/daily/enrichment.md` (it also covers
`provider_requests.py`; check its `covers:`). Measured on master (crapper, full-suite coverage):

| Function | File | CC | Cov | CRAP |
| --- | --- | --- | --- | --- |
| `enrich` | `src/app/core/daily/enrichment.py` | 13 | 66.7% | 19.3 |
| `reusable` | `enrichment.py` | 15 | 100% | 15.0 |
| `grounded_summary` | `enrichment.py` | 14 | 87.5% | 14.4 |
| `publish_day` | `enrichment.py` | 11 | 87.5% | 11.2 |
| `source_row` | `enrichment.py` | 11 | 100% | 11.0 |
| `parse_review` | `enrichment.py` | 8 | 66.7% | 10.4 |
| `parse_jev` | `src/app/core/daily/provider_requests.py` | 11 | 100% | 11.0 |

Goal: each under CRAP 10 and no function of the two files at 10 or above; behavior exactly
unchanged: same results, exceptions and messages, log events and fields, SQL, journal calls and
their order (reservation before dispatch), caps, cache keys, order of checks where the first failing
check names a reason.

## Steps (tests first, then code)

1. Read `AGENTS.md` ("Feature Docs Next To Code", "Code Changes", "Validation"), the two files, the
   doc, `src/app/storage/provider_journal.md`, and the tests:
   `tests/unit/test_daily_enrichment.py tests/unit/test_daily_publish_day.py
   tests/unit/test_provider_requests.py tests/unit/test_provider_requests_parse.py
   tests/unit/test_cli_daily_publish.py` (and `tests/unit/daily_fixtures.py`).
2. Characterization tests first for the uncovered branches (coverage of the seven functions:
   `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" --cov=src/app/core/daily --cov-report=term-missing <tests>`;
   use a path source, not a module name, see `docs/troubleshooting.md`). They pass on the current
   code. Assert real state (returned rows, journal rows and states, log fields, order of calls), not
   only "no exception". Monkeypatch only names the patched module itself reads
   (`tests/unit/test_monkeypatch_targets.py` guards this).
3. Refactor: extract small named helpers (one decision each); keep public names and signatures; no
   new abstractions beyond what removes branches. If the doc names a function you rename, or a rule
   gains a test, update the doc in the same change (behavior does not change).
4. Final checks (once each, in this order, from the worktree root; report last lines and exit codes):
   - `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" -n auto | tail -1`
   - `PYTHONPATH=src make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python 2>&1 | tail -5`
   - `env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 ~/tools/unclebob/crapper/crapper src/app/core/daily/enrichment.py src/app/core/daily/provider_requests.py`
     (report every function at CRAP >= 8, before and after)
   - `~/tools/unclebob/dryer/dryer --threshold 0.8 src/app/core/daily/enrichment.py src/app/core/daily/provider_requests.py src/app/core/jev.py`
     (report pairs)
   - mutator, one file at a time:
     `env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 ~/tools/unclebob/mutator/mutator --use-existing-coverage --test-command "/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_daily_enrichment.py tests/unit/test_daily_publish_day.py tests/unit/test_provider_requests.py tests/unit/test_provider_requests_parse.py" <file>`
     for both files. Kill survivors with tests or give a one-line reason each. Hand mutations only
     with `PYTHONDONTWRITEBYTECODE=1` (a stale `.pyc` hid a mutant before).
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python scripts/check_code_docs.py; echo exit=$?` (alone, last)

## Report (your final message)

Files changed, one line each; new tests and which branch each covers; crapper table before/after;
dryer pairs; mutator per file (sites, killed, survived, uncovered, what you did with survivors); doc
edits; anything you could not do, one line each. Be brief.
