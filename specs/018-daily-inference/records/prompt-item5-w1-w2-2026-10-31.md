# Prompt: spec 018 item 5, world stream steps W1 and W2 (2026-10-31)

You implement steps **W1** and **W2** of the world news plan, as **two PRs** (W2 branches from W1
or waits for its merge; say which). Repo: `ai-news-collector`
(`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`). Report in English. Do not merge, tag or deploy; no
ssh; no paid calls.

## Rules

- Work only in your own isolated worktree from `origin/master` (`git fetch origin` first). Never
  edit, commit or pull in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself; you may read files
  there (prompts, `venv1`). Run Python as `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python`
  (venv1 points at the main folder's src).
- Read `AGENTS.md` first and follow it: the feature doc next to the main module **before** code,
  small patches in the style of the surrounding code, ASCII code, tests per rule.
- Network: W1 none. W2 may download at most 3 real GDELT files for a manual smoke check; unit tests
  use small fixture files only.

## Read

1. The plan: `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/8230bf51-ec40-4f65-b975-34c791a2cee9/scratchpad/plan-item5-world-sources-2026-10-31.md`
   (all of it; W1 and W2 are in section 6.2; filters in section 3; GDELT facts in 1.2). The filter
   prototypes `kw.py` and `filt.py` and the sample `world-sample-2026-10-31.jsonl` are in the same
   scratchpad directory.
2. `specs/018-daily-inference/spec.md` (FR-014..FR-018, FR-016) and `voice.md`, on `origin/master`.
3. `src/app/core/archive/capture.md` and `src/app/core/ingestion/pipeline.md` for patterns.

## Owner decisions and facts to apply (2026-10-31)

- Yes: a footer credit "News discovery: GDELT Project" with a link (GDELT terms require citation).
- Yes: a separate Jev budget for the world stream, $0.05 per day, inside the approved $3 per month.
- Production server: 4 TB monthly traffic (the ~25 GB/month of GDELT files is fine), **but only
  3.6 GB of free disk (25 GB, 85% used) and 2 GB RAM**. So W2 must stream: download one file at a
  time to a temp file or memory, parse, keep only matching rows, delete it; never keep raw GDELT
  files; bounded memory (no whole-day lists of raw rows). Write this into the doc as an invariant
  with a test.
- Fix the two filter bugs the research found: `slguardian.org` is not a finance domain; own-source
  domain matching must cover subdomains (`feeds.arstechnica.com` matches `arstechnica.com`).

## Steps

1. **W1 PR** (no network): copy the plan into
   `specs/018-daily-inference/records/plan-item5-world-sources-2026-10-31.md` and this prompt into
   the same `records/` directory; add the two owner decisions above to the spec's "Owner decisions"
   section; then do W1 as the plan describes (doc `src/app/core/world/world.md` registered like the
   other docs, the keyword filter module with its constants, tests on fixtures taken from the
   sample, the two bug fixes). Measure the filter on the sample and put kept/dropped counts in the
   PR body.
2. **W2 PR**: the GKG reader as the plan describes (file names for a UTC day, primary and
   translation sets, streamed download and parse, title extraction, missing-file handling as
   `partial` per the plan's rule, no database). Tests with tiny fixture files (zip and plain), a
   missing file, a malformed row, and the streaming invariant (memory bounded, no file left on
   disk). One manual smoke run over at most 3 real files; put its counts in the PR body.
3. **Checks** for each PR: ruff, scoped tests, then `make lint PYTHON=...` and the full pytest with
   `-o addopts="" | tail -1` for the pass count. `scripts/check_code_docs.py`.
4. **PRs**: commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`;
   `gh pr create --base master` with titles `feat(018): world stream W1 keyword filter` and
   `feat(018): world stream W2 GDELT reader`; bodies list changes, checks, numbers, and end with
   `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final message)

Both PR links; files; checks with counts; filter numbers on the sample; smoke-run numbers; anything
decided by you (one line each); questions for the owner only if about money or what readers see.
