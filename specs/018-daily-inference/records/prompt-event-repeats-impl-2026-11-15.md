# Prompt (Claude agent, Sonnet): spec 018 F10, event-level repeats in the bulletin (2026-11-15)

Worktree (work only here): `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/event-repeats`,
branch `feat/018-event-repeats`. Do not commit, push or use gh. No network, no ssh, no paid calls
(tests use fakes). Do not spawn sub-agents. Read `AGENTS.md` first (TDD, feature docs, exceptions).

Commands (from the worktree root; `V=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin`):
- tests: `PYTHONPATH=src $V/pytest -q -o addopts= <files>`
- lint at the end: `PYTHONPATH=src make lint PYTHON=$V/python`; docs: `$V/python scripts/check_code_docs.py`

## Why

FR-022 review of 2026-11-09..14: 7 of 29 published stories were repeats. The same event ran three
days from different outlets with different titles ("United won't let your AI agent book your
flight", "United Airlines blocks AI agents from booking flights", "United Airlines bans AI bots
from booking flights"), once twice in one bulletin; the same Reuters article ran two days apart.
Today only world candidates are compared, only with D-1, only by URL or `cluster_key` of the title
(`_world_candidates` in `src/app/usecases/bulletin/day_input.py`, rule in
`src/app/core/bulletin/builder.md`). The owner approved one extra model call a day (2026-11-15).

## Read first

`src/app/usecases/bulletin/daily.py` and `daily.md`, `day_input.py`, `writer_run.py`
(`open_writer`, `Writer.ask`), `src/app/core/bulletin/builder.py` (`Candidate`, `DayInput`,
`MIN_CONFIDENCE`, how `event_key` merges candidates into one story), `writer.py` (`writer_body`,
`_answer`, `WRITER_MODEL`), `tests/unit/test_bulletin_daily.py` (fake factories).

## Rules to implement (write them into the docs first, then tests, then code)

R1, free check, in `day_input.py`. Replace the D-1 rule: a candidate of D, digest or world, is
left out when a ready stored bulletin of D-1 .. D-`REPEAT_DAYS` (constant 3, defined in the new
core module) has a story with the same link URL or the same `cluster_key` of its title. Missing,
skipped or unreadable days are ignored one by one. Update the rule and test names in `builder.md`
and the existing tests of the old rule (`test_world_candidates_not_compared_beyond_yesterday`,
`test_digest_candidates_ignore_yesterday` and their neighbours) to the new behavior.

R2, model check, new pure core module `src/app/core/bulletin/repeats.py` with its feature doc
`src/app/core/bulletin/repeats.md` (header, sections and registration as AGENTS.md "Feature Docs
Next To Code" says; the module docstring names the doc). No I/O imports in the core module.
- Input: the `DayInput`, the published stories of the last `REPEAT_DAYS` ready bulletins (day,
  shown headline or title, title), and an `ask` callable like `Writer.ask`
  (`body -> (data, reason)`).
- Listed candidates: only those that can be shown (`world_change` not `none`, confidence at least
  `MIN_CONFIDENCE`), at most `REPEATS_MAX_CANDIDATES` (40) by confidence, ids `c1..cN` with title
  and outlet; published stories ids `p1..pM` with day and title. Titles cut to 200 characters.
- No listed candidate: no call. No published story and fewer than two candidates: no call.
- One request, built like `writer_body` (`request_body`, `WRITER_MODEL`, own prompt
  `REPEATS_PROMPT`, version `REPEATS_VERSION = "bulletin-repeats-1"` named in the prompt, small
  `REPEATS_MAX_OUTPUT`). The prompt asks for JSON only:
  `{"repeats": [{"candidate": "c3", "published": "p2"}], "same_event": [["c1", "c4"]]}`.
  A repeat: the candidate reports the same event as a published story and its title shows no new
  development (a decision, ruling, number or step the published story did not have). `same_event`:
  today's candidates that report one event. When unsure, the model must not list the candidate.
- Answer check, strict: a JSON object with exactly these two keys, known ids only, a candidate at
  most once in `repeats` and in at most one `same_event` group, groups of two or more. Anything
  else is `invalid_answer`: nothing is dropped or merged by the model (the bulletin must still go
  out). A provider reason from `ask` is recorded the same way, nothing dropped.
- Effect: a candidate in `repeats` is removed from `DayInput.candidates`. Candidates of one
  `same_event` group get the `event_key` of the group's best member (confidence, then listing
  order), so the builder makes one story with all outlets. Candidates not listed are untouched.
- Summary (plain dict, goes to `numbers["repeats"]`): `version`, `model`, `reason` (None when
  applied), `candidates`, `published`, `dropped` (list of `{"title", "published_day",
  "published_title"}`), `merged` (list of title lists).

R3, wiring in `daily.py`: only `run_daily` runs the model check, after `load_day_input` and before
`build_bulletin`, only when the DeepSeek key is set (same condition as the writer), through
`env.writer_factory(env.settings, today)` (the writer's journal of the real day and its daily
cap; the two calls of a day have different bodies, so the journal keeps both). Log one event
`bulletin_repeats` with the summary. The published stories are read by a small function in
`day_input.py`. `prepare_bulletin` stays usable without the check for the other commands. Update
`daily.md` (Behavior, Mermaid flow, Code map, Tests) and note there that the writer's `cost_usd`
is the journal's total of the day and so includes this call.

## Tests (first, each seen failing for the expected reason)

Core (`tests/unit/test_bulletin_repeats.py`, fake `ask`): repeat is dropped; unknown id, extra
key, duplicate candidate, one-member group each give `invalid_answer` with nothing changed;
provider reason keeps everything; same_event sets one event key and `build_bulletin` then yields
one story with both outlets; below-threshold and `none` candidates are not listed; no call cases;
the request names `REPEATS_VERSION` and holds titles but no article text.
Loader: R1 cases (digest candidate dropped by URL at D-2 and by title key at D-3; D-4 not
compared; unreadable day ignored).
Daily (`tests/unit/test_bulletin_daily.py` or a new file if it would pass 1000 lines): the check
runs before the build and its summary is in the stored `numbers`; no DeepSeek key means no call.

## End checks, once each, in this order

Scoped tests of the touched test files, `tests/unit/test_code_docs.py`, `make lint`, then
`export PYTHONPATH=src PATH=$V:$PATH PIP_NO_INDEX=1`,
`~/tools/unclebob/crapper/crapper <changed src files>` (CRAP under 10),
`~/tools/unclebob/dryer/dryer --threshold 0.8 <changed src files>`,
`~/tools/unclebob/mutator/mutator --use-existing-coverage --test-command "$V/pytest -q -o addopts= tests/unit/test_bulletin_repeats.py" src/app/core/bulletin/repeats.py`
(kill survivors with tests or give the reason). Do not run the full suite: CI does.

## Final message (brief)

Files changed; each rule with its tests; the last lines of each end check; every decision you
made that this prompt did not state (one line each); anything not done and why.
