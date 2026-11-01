# Prompt: spec 018 item 3, model writer with grounding (2026-11-01)

You implement item **3** of spec 018 as one PR, branch `feat/018-bulletin-writer`. Repo:
`ai-news-collector` (`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`). Report in English. Do not
merge, tag or deploy; no ssh.

## Rules

- Your own isolated worktree from `origin/master` (`git fetch origin` first). Never edit, commit,
  check out or pull in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself; you may read files
  there. Scratch worktrees named with `item3`; never remove one you did not create.
- Run Python as `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python`.
  pytest prints no summary by default: use `-o addopts="" ... | tail -1`.
- Read `AGENTS.md` first and follow it, and the ub-mode skill (`~/.claude/skills/ub-mode`; its
  "Repository rules come first" section applies). Doc first, then a failing test you saw fail for
  the expected reason, then the smallest code. Small patches in the surrounding style.
- **No paid calls.** The model runs only through fakes and recorded fixtures. A real run on one
  day is a separate step after review.

## Read

1. `specs/018-daily-inference/spec.md`: ER-1..ER-12 (especially ER-1, ER-2, ER-3, ER-6, ER-8,
   ER-9, ER-11, ER-12), User Story 1 scenario 4, FR-004, FR-005, FR-012; `voice.md` (voice,
   structure, never-list, the hand-written samples: the target quality).
2. `src/app/core/bulletin/builder.md` and `builder.py`, `render.py`, `phrases.json`,
   `src/app/storage/bulletin_input.py`, and the `bulletin build --dry-run` CLI (item 2).
3. `src/app/core/daily/signals_brief.py` (DeepSeek call, prices, `parse_brief` grounding check,
   cap through the provider journal) and its doc; reuse its pieces rather than copying them.
4. Archive texts: `src/app/core/archive/capture.md`, `src/app/storage/archive.py` (text by
   `url_canonical_hash`, origin `source_page`); the world stream's `archive_text_source` in
   `src/app/core/world_text.py` (same reading for world candidates).

## What to build

- New feature doc next to the main module (for example `src/app/core/bulletin/writer.md`), with
  Behavior (Mermaid flow), Decisions, Invariants, Code map, Tests; registered in `docs/README.md`,
  `README.md`, `src/app/README.md`.
- **One model call per day** (FR-005), DeepSeek flash by default (prices as in `signals_brief.py`),
  through the provider journal with its own daily cap line (writer `$0.10` per UTC day, FR-012;
  same per-real-day shape as the world journal: one file per UTC day, fixed cap, `--max-usd` only
  lowers it). Input: the builder's selected stories, each with its full archive text (cut to a
  named limit) or, without text, title and summary; output in JSON: headline of the day (at most 8
  words, official notice voice), per story a headline, a site note of 3-6 sentences, a Telegram
  note of 1-2 sentences, a short gloss for unknown names; non-English sources translated
  (ER-12).
- **Prompt**: built from `voice.md` rules and the editorial rules (retell in own words, short
  quotes only in quotation marks, vendor claims attributed, no words in real people's mouths, no
  new facts in framing, harm never framed as success). The prompt text lives in a versioned file
  or constant (`WRITER_VERSION`); a test pins its key rules.
- **Grounding** (FR-005, User Story 1 scenario 4): every sentence passes a check like
  `parse_brief` (names and numbers present in the cited original text, in the source language or
  its transliteration where feasible; say what you can and cannot check). A failing sentence is
  dropped; a story left without sentences falls back to its title with outlet (origin `title`);
  a failing headline of the day falls back to item 2's title-based headline. Never-list check
  (ER-4, ER-2) on all model text. Quote length limit (ER-9) checked.
- **Failure**: model unavailable, cap reached, invalid JSON -> the whole bulletin falls back to
  item 2's title-only stories and says so (`origin` per story, a reason in the summary); never
  raises into callers.
- **CLI**: `ai-news bulletin build --date D --dry-run [--write] [--json] [--max-usd X]`: without
  `--write` it behaves exactly as item 2 (no call); with `--write` and `DS_API_KEY` it calls the
  model (exit 2 without the key). Still no storage, job or page (item 4).
- Tests on recorded fixtures: grounded sentences kept; invented name or number dropped; story with
  all sentences dropped -> title fallback; headline fallback; cap and journal per UTC day; outage
  fallback; never-list; long quote dropped; translation case (non-English source, English output,
  names grounded); the prompt pins its rules; no call without `--write`.

## Checks

ruff on `src tests`; scoped tests; `make lint PYTHON=...`; full pytest `-o addopts="" | tail -1`;
`scripts/check_code_docs.py --diff origin/master --strict` run alone after your last commit, report
its exit code. mypy: fix `no-any-return` with `cast` or a typed local, never `# type: ignore`.
Advisory: `~/tools/unclebob/dryer/dryer` and `~/tools/unclebob/crapper/crapper --no-coverage` on
changed source files (report duplicates >= 0.8, complexity >= 10; delete `.metrics/`).

## PR

Copy this prompt into `specs/018-daily-inference/records/` of your branch. Commit messages end with
a `Co-Authored-By:` line naming the model that wrote them. `gh pr create --base master`, title
`feat(018): bulletin writer with grounding (item 3)`; body lists changes, checks with counts, a
fixture bulletin with model text (marked as fixture), and ends with
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final message)

PR link, branch, worktree path; files; checks with counts and the doc-check exit code; the fixture
bulletin; estimated tokens and cost per day (from the prompt size and a typical day of 8-10
stories); what the grounding check can and cannot catch; the exact command for the later real run;
anything decided by you (one line each); questions for the owner only if about money or what
readers see, each as yes/no with a recommendation.
