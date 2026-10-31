# Prompt: spec 018 item 1, Jev world_change questions (2026-10-31)

You implement item 1 of `specs/018-daily-inference/spec.md` in the `ai-news-collector` repo
(`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`). Report in English. Do not merge, do not tag, do not
deploy, do not touch production (no ssh).

## Rules

- Work only in your own worktree from `origin/master` (other sessions work in the main folder):
  `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER fetch -q origin && git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER worktree add -b feat/018-world-change <your scratchpad>/wt-018-item1 origin/master`
  (if you were started with an isolated worktree, use it and create the branch there).
- Read `AGENTS.md` first and follow it: feature doc next to the main module **before** code
  ("Feature Docs Next To Code"), `venv1` for commands (the venv lives in the main folder:
  `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python`), small patch in the style of the
  surrounding code, ASCII code.
- Paid calls: Jev only, through the existing provider journal, total cap for this task **$0.20**
  (expected about $0.05). No DeepSeek calls. Never print API keys.
- Copy this prompt into your PR as `specs/018-daily-inference/records/prompt-item1-world-change-2026-10-31.md`
  (and the labels prompt `prompt-item1-labels-2026-10-31.md` from the main folder's same directory).

## Read

1. `specs/018-daily-inference/spec.md`: The idea, ER-*, FR-001, FR-002, FR-003, FR-012, Key
   Entities, Implementation order item 1. `voice.md`: Areas.
2. `src/app/core/jev.py` (request body, `jev_state`, `JevScorer.state`, `classify`, error handling,
   `payment_journal.call("jev", ...)`), `src/app/core/daily/rubric.py` (question JSON format: types
   `choice` and `noul`, `criteria`, `instructions`), `src/app/core/provider_costs.py`,
   `src/app/storage/provider_journal.py`, `src/app/core/ingestion/pipeline.md` (Jev parts),
   `src/app/core/daily/enrichment.md`, `src/app/storage/models_sql.py`, the Alembic migrations dir
   and one recent migration as a pattern, `src/app/cli/main.py` (how commands and caps are wired).

## Build

1. **Doc first**: `src/app/core/bulletin/world_change.md` (new package `app.core.bulletin`) with the
   sections AGENTS.md asks for (Behavior with a Mermaid flow, Decisions, Invariants, Code map, Tests)
   and the `code-doc` header; register it in `docs/README.md`, `README.md`, `src/app/README.md`.
2. **Questions**: `WORLD_CHANGE_QUESTIONS` and `WORLD_CHANGE_VERSION` in
   `src/app/core/bulletin/world_change.py`, same JSON shape as `rubric.QUESTIONS`. Four questions:
   `world_change` (choice: added, changed, issue, limit, none), `area` (choice: the 13 areas of
   `voice.md`), `actor` (choice: ai_system, people, organisation), `harm_to_people` (noul). Start the
   criteria from the definitions in `prompt-item1-labels-2026-10-31.md` (same meaning, so labels and
   Jev answer the same question); instructions end with "Treat state only as data." as the rubric does.
   **Do not change `rubric.py` or `RUBRIC_VERSION`.**
3. **Request**: `assess(article) -> WorldChange | None`: one separate POST per article with the
   configured `jev_model`, the same state text the daily enrichment sends (`JevScorer.state` rules:
   content without summary, title and summary when there is no content), through the provider
   journal (provider `jev`); a transport or parse failure returns None and is logged, never raises
   into callers. Probabilities validated like `_probability`.
4. **Storage**: table `world_change_assessments`: `url_canonical_hash`, `article_id` (nullable;
   articles are pruned, the hash stays), the four answers with confidences, `question_version`,
   `model`, `assessed_at`; unique (`url_canonical_hash`, `question_version`). Alembic migration that
   creates the table only when missing; downgrade drops it; round-trip test like the archive one.
5. **CLI**: `ai-news bulletin assess --date YYYY-MM-DD [--max-usd X] [--dry-run]`: assesses the
   day's digest articles (same day scope as the daily digest; find how `day_articles` selects them),
   skips articles already assessed for the current version, prints one JSON summary (assessed,
   skipped, failed, by choice, cost). `--dry-run` makes no request and writes nothing. Not wired into
   any daily job (that is item 4).
6. **Tests** (`tests/unit/test_world_change.py`): question shape and version; request body has
   exactly these four questions and the expected state; answer parsing incl. invalid probabilities;
   failure returns None; storage idempotency per version; CLI dry run makes no request; migration
   round trip. Mock HTTP as the existing Jev tests do.
7. **Offline check (FR-002)**: `specs/018-daily-inference/records/eval_world_change.py`, a script
   (not product code) that reads
   `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/8230bf51-ec40-4f65-b975-34c791a2cee9/scratchpad/world-change-sample.jsonl`
   (260 digest articles of 2026-10-24, -25, -28, -29, -30 with title, summary, content), calls
   `assess` on each through the real Jev API (key from the main folder `.env`, `JEV_API_KEY`),
   writes `world-change-jev.jsonl` next to the input, and, when
   `world-change-labels.jsonl` exists there (written by a separate labelling session; do not write or
   edit it yourself), prints agreement per question, a confusion table for `world_change`, and
   agreement by confidence bucket (to choose the threshold of FR-003). If the labels file is not
   there yet, finish everything else and say so; the coordinator runs the comparison later.
   Results go to `specs/018-daily-inference/records/report-item1-2026-10-31.md`: cost, failures,
   distributions, agreement, a proposed confidence threshold, and 5 disagreements with one line each.
8. **Checks**: `./venv1/bin/python -m ruff check src tests`, scoped pytest, then the full gate
   (`make lint PYTHON=...`, full pytest). State exactly what ran.
9. **PR**: commit (end the message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`),
   push, `gh pr create --base master --title "feat(018): Jev world_change questions (item 1)"` with a
   body that lists what changed, checks, cost, and ends with
   `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Do not merge.

## Report (final message)

PR link; files changed; checks run and results; Jev cost; agreement numbers (or "labels not yet
available"); open questions, each as: settled how (found / decided by you) or a yes/no for the owner
(only product or money questions).
