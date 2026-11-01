# Report: spec 018 item 2, bulletin builder (2026-11-01)

Implementer report (background agent, model sonnet), saved by the coordinator. PR #192, branch
`feat/018-bulletin-builder`. No paid calls.

## Files

New in `src/app/core/bulletin/`: `builder.md`, `builder.py`, `phrases.json`, `phrases.py`,
`render.py`; `src/app/storage/bulletin_input.py` (read-only loader); `tests/unit/test_bulletin_builder.py`
(32 tests). Changed: `src/app/cli/main.py` (`bulletin build --date D --dry-run [--json]`),
`src/app/config/settings.py` (`world_stream_in_bulletin`, env `AINEWS_WORLD_STREAM_IN_BULLETIN`,
default off), `voice.md` (points to the JSON), doc registrations, `docs/cli.md`,
`docs/configuration.md`, `pyproject.toml` package data, `tests/unit/test_world_storage.py` (bulletin
loader is the one allowed reader of world tables, FR-016).

## Checks (implementer)

ruff, `make lint` (mypy 257 files, pylint 10.00); full pytest 1844 passed, 1 skipped;
`check_code_docs.py --strict` exit 0 (11 docs); dryer none; crapper max 9.

## Smoke

Not on real data: the local DB (`data/ai_news.db`, Oct 17) has no `world_change_assessments`. The PR
body has a bulletin from a hand-made fixture modelled on the 2026-10-30 sample.

## Decided by the implementer

- `--json` prints the object only; without `--dry-run` exit 2; skipped day logs `bulletin_skipped`,
  exit 0; no digest exit 2.
- No stored answers -> skipped `no_assessments`; no signals row -> `no_signals`.
- Busy day needs at least 7 stored days for the median, else ordinary.
- Numbers line counts events from `event_counts`; launch line only when both counts > 0.
- "Among them": top issue with actor `people` or `organisation`; extra AI-actor issues counted as
  incidents; harm if any member of the event has harm >= 0.7.
- Key results get a reaction only when neither the rubric nor the first Cooperation story got one.
- `ai_issue_with_fix` reaction never picked in item 2 (item 3 may use it).
- Headline: a title with no clause boundary within 8 words is skipped; none fits -> no headline.
- Events merged by top story of the daily signals, then by title key from `cluster_key`.

## Open point

On the fixture the headline came out "CROSBY, AN AI-FIRST LAW FIRM*" (cut at the first comma).

## Fixes after review (commit 9b0f2e4, rebased on W7)

Headline cut only after `:`/`;`, before a dash or but/while/because/although (else skip, none ->
no headline); busy median over ready days before D; outcome-claiming area reactions removed (Work,
Money, Infrastructure, Science, Health; Faith/Culture dialogue kept); event representative among
non-`none` members; harm counting stated; top-story match by URL then canonical hash;
`bulletin_assessed_share` log and `--json` counts; `voice.md` 7-day minimum; second numbers-line
variants; survivors M18, M22, M26 closed. Mutations of the fixes all caught. Checks: `make lint`
clean; full pytest 1863 passed, 1 skipped; `check_code_docs.py --strict` exit 0. Coordinator
checked the headline and median code and CI (lint, tests pass) and merged (owner's blanket yes for
018 PRs after clean review, 2026-11-01).
