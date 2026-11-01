# Prompt (Codex, gpt-6.1-sol high): bulletin outlet names without feed labels (2026-11-01)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch
`fix/018-bulletin-outlet-name`, already checked out from origin/master):
`/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/codex-outlet`. Do not touch any other directory. Do not run git commit, push or any gh command:
the coordinator commits and opens the PR. No network, no paid calls.

## Why

In the bulletin, a story's outlet is the source name from `sources.yaml`, which carries internal feed
labels: the real run printed "(TechCrunch (main feed))". Readers should see "TechCrunch". World
stream stories show the bare domain with "www." ("www.bbc.com"). The digest at `/daily` keeps its
names: change only the bulletin.

## Steps (in this order; repo rule: doc first, then a failing test, then code)

1. Read `AGENTS.md`, `src/app/core/bulletin/builder.md`, `src/app/storage/bulletin_input.py`,
   `tests/unit/test_bulletin_builder.py`.
2. Edit `src/app/core/bulletin/builder.md` (Behavior): add one rule: "The outlet shown is the source
   name without a trailing parenthesised label (\"TechCrunch (main feed)\" -> \"TechCrunch\"); a world
   story shows its domain without a leading `www.`. Tests: `test_outlet_name_drops_feed_label`."
   Keep lines at most 100 characters.
3. In `tests/unit/test_bulletin_builder.py` add `test_outlet_name_drops_feed_label`, testing a
   small pure helper `outlet_name(name: str) -> str` that you will add to
   `src/app/storage/bulletin_input.py`: cases "TechCrunch (main feed)" -> "TechCrunch",
   "Machine Learnings (newsletter/feed)" -> "Machine Learnings", "Simon Willison's Weblog" unchanged,
   "www.bbc.com" -> "bbc.com", "bbc.com" unchanged, "" stays "". Run it and see it fail (import
   error) with:
   `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/pytest -q -o addopts="" tests/unit/test_bulletin_builder.py -k outlet_name | tail -3`
4. Add `outlet_name` to `src/app/storage/bulletin_input.py` (one regex for a trailing
   `\s*\([^)]*\)` and one for a leading `www.`), and use it at both places where `outlet=` is set
   (digest: the source name or hostname; world: `item.source_domain`). Smallest change, same style.
5. Run, from `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/codex-outlet`:
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/pytest -q -o addopts="" tests/unit/test_bulletin_builder.py tests/unit/test_bulletin_writer.py | tail -1`
   - `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python -m ruff check src tests`
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python scripts/check_code_docs.py`; echo exit=$?
   Fix anything that fails.

## Report (your final message)

Files changed with a one-line summary each; the failing-test output of step 3; the outputs of step 5
(last lines and the exit code). Nothing else.
