# Prompt (Claude Opus agent): ub-mode pass 2, bulletin modules (2026-11-02)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch `refactor/ub-bulletin`,
checked out from origin/master): `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/ub-bulletin`.
Do not touch any other directory (the main folder `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` is
read-only for you except its `.venv`). Do not run git commit, push, stash or any gh command. No
network, no paid calls (tests use fakes; never call Jev or DeepSeek). Do not spawn sub-agents: a
separate reviewer reviews after you.

Speed rule: while working run only the feature tests (list below) and `ruff` on changed files; at
the end run the full suite, `make lint`, crapper, dryer and mutator once each, in that order; after a
fix rerun only the check that failed.

## Scope

Whole-repo ub-mode pass (owner yes 2026-11-02), money paths first; module 2 = spec 018 bulletin
code (backlog T4). Measured on master (crapper, full-suite coverage):

| Function | File | CC | Cov | CRAP |
| --- | --- | --- | --- | --- |
| `validate_phrases` | `src/app/core/bulletin/phrases.py` | 18 | 91.7% | 18.2 |
| `_digest_candidates` | `src/app/storage/bulletin_input.py` | 12 | 100% | 12.0 |
| `run_assessment` | `src/app/core/bulletin/world_change.py` | 10 | 87.5% | 10.2 |
| `sentence_error` | `src/app/core/bulletin/writer_grounding.py` | 10 | 90.0% | 10.1 |

Goal: each of these under CRAP 10 (and no other function of these four files at or above 10),
behavior exactly unchanged: same results, exceptions and messages, log events and fields, SQL,
order of checks (in `sentence_error` the first failing check names the drop reason, so the order is
behavior), money caps and journal use in `run_assessment`.

## Steps

1. Read `AGENTS.md` ("Feature Docs Next To Code", "Code Changes", "Validation"), the four files,
   their docs (`src/app/core/bulletin/builder.md` covers phrases and bulletin_input;
   `writer.md` covers writer_grounding; `world_change.md` covers world_change) and the tests:
   `tests/unit/test_bulletin_builder.py tests/unit/test_bulletin_writer.py tests/unit/test_world_change.py
   tests/unit/test_bulletin_daily.py`.
2. Characterization tests first for the uncovered branches (coverage of the four functions; run
   `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" --cov=src/app/core/bulletin --cov=src/app/storage --cov-report=term-missing <tests>`;
   use path sources, not module names, see `docs/troubleshooting.md`). They pass on the current
   code. Put them in the existing test files of each feature.
3. Refactor: extract small named helpers (one decision each); keep public names and signatures; no
   new abstractions beyond what removes branches. If a doc names a function you rename or a rule
   you touch, update that doc in the same change (docs describe behavior, which does not change;
   add new test names to the rules they check).
4. Final checks (once each, in this order, from the worktree root; report last lines and exit codes):
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" -n auto | tail -1`
   - `PYTHONPATH=src make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python 2>&1 | tail -5`
   - `env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 ~/tools/unclebob/crapper/crapper src/app/core/bulletin/phrases.py src/app/storage/bulletin_input.py src/app/core/bulletin/world_change.py src/app/core/bulletin/writer_grounding.py`
     (report every function at CRAP >= 8 with CC, coverage, CRAP, before and after)
   - `~/tools/unclebob/dryer/dryer --threshold 0.8 src/app/core/bulletin/*.py src/app/storage/bulletin_input.py`
     (report pairs)
   - mutator, one file at a time, each with its narrow tests:
     `env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 ~/tools/unclebob/mutator/mutator --use-existing-coverage --test-command "/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= <tests of that file>" <file>`
     for the four files (phrases + bulletin_input -> test_bulletin_builder.py; world_change ->
     test_world_change.py; writer_grounding -> test_bulletin_writer.py). Kill survivors with tests or
     give a one-line reason each.
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python scripts/check_code_docs.py; echo exit=$?` (alone, last)

## Report (your final message)

Files changed, one line each; new tests and which branch each covers; crapper table before/after;
dryer pairs; mutator per file (sites, killed, survived, uncovered, what you did with survivors); any
doc edits; anything you could not do, one line each. Be brief.
