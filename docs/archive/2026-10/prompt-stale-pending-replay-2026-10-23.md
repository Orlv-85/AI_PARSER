# Prompt: stop replaying archive-old pending candidates (2026-10-23)

You are the implementer for `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. Read `AGENTS.md` first and
follow it. Work only in the worktree below; do not write to git in the main folder. Do not merge,
tag or touch prod.

## Facts (prod, read-only, 2026-10-22)

- The OpenAI feed (`https://openai.com/news/rss.xml`) lists its whole archive since 2015 (~1360
  items). 1044 of its admission candidates are `pending` (`admission_decisions.provider_status`),
  by publication year: 2015-2019 ~300, 2020-2023 ~280, 2024 340, 2025 80, 2026 46.
- Before each source is fetched, `_replay_pending_for_source` (`src/app/core/ingestion/pipeline.py`)
  replays up to `PENDING_REPLAY_LIMIT` (50) pending candidates, oldest `updated_at` first
  (`list_pending`, `src/app/storage/admission.py`). Every replay of a body candidate is a paid Jev
  call. So each run spends ~50 Jev calls on 2016-2024 articles that would never reach a daily
  digest (it is built by publication day) and are not news any more.

## Decided by the coordinator (2026-10-23, agent)

- A pending body candidate (`kind == "article"`) whose stored candidate has a publication date
  (`published_at`, or `publication_day` when no time) older than
  `PENDING_REPLAY_MAX_AGE_DAYS = 30` days before the run is settled without a Jev call:
  `settle_pending(..., provider_status="settled", reason="stale_pending")`. It is not stored as an
  article. Candidates without a publication date and HTML link placeholders are replayed as now.
- Only the replay path changes. Fresh candidates from a feed are screened as now.
- Why: a stale pending candidate is archive material, not news; screening it costs a paid call per
  run and delays the replay of fresh pending candidates of the same source. Readers do not see a
  change: these candidates never reached the site.
- Stale candidates must not count toward the replay limit: select fresh pending rows first, or
  settle the stale ones before taking the 50 (pick the simplest correct way, explain it in the report).

## Setup

```
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch origin
git worktree add ../AI_PARSER-wt-stale-pending -b fix/stale-pending-replay-20261023 origin/master
cd ../AI_PARSER-wt-stale-pending
```

Checks in the worktree: `PYTHONPATH=src ../AI_PARSER/venv1/bin/python ...`,
`PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest ...`.

## Steps (doc first)

1. `src/app/core/ingestion/pipeline.md`: in Behavior, extend the rule "Before a source is fetched,
   its pending candidates (at most `PENDING_REPLAY_LIMIT`) are replayed ..." with the stale rule
   above (name `PENDING_REPLAY_MAX_AGE_DAYS`, not the number) and its tests; add one Decisions row
   ("Stale pending candidates are settled without screening | <why above>, decided 2026-10-23
   (agent)").
2. Code: `PENDING_REPLAY_MAX_AGE_DAYS = 30` next to `PENDING_REPLAY_LIMIT` in `pipeline.py`; the
   change in `_replay_pending_for_source` and, if needed, `list_pending`. Read how the candidate
   payload stores the date (`_candidate_payload`, `_article_from_candidate`) before writing the age
   check; a date that cannot be parsed counts as "no date" (replayed as now).
3. Tests in `tests/unit/test_semantic_admission_pipeline.py` (reuse `Scenario`):
   - `test_stale_pending_candidate_is_settled_without_screening`: a pending article candidate
     published 31+ days ago: no Jev request, row settled with reason `stale_pending`, no article.
   - `test_recent_and_undated_pending_candidates_are_still_replayed`: 29 days old and undated
     candidates are screened as before.
   - `test_stale_pending_does_not_use_the_replay_limit`: with more than `PENDING_REPLAY_LIMIT`
     stale rows plus one fresh pending row, the fresh one is replayed in the same run.
4. Checks (all must pass, files ASCII):
   ```
   PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest tests/unit/test_semantic_admission_pipeline.py tests/unit/test_code_docs.py
   PYTHONPATH=src ../AI_PARSER/venv1/bin/python scripts/check_code_docs.py --diff origin/master --strict
   make lint PYTHON=../AI_PARSER/venv1/bin/python
   PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest
   ```
5. Commit, push, PR:
   ```
   git add -A
   git commit -m "fix(admission): settle archive-old pending candidates without screening" -m "The OpenAI feed lists its archive since 2015; 1044 pending candidates (mostly 2016-2024) were replayed 50 per run, each a paid Jev call. Pending body candidates published more than PENDING_REPLAY_MAX_AGE_DAYS (30) days ago are now settled as stale_pending without a call and do not use the replay limit." -m "Co-Authored-By: <your model name> <noreply@anthropic.com>"
   git push -u origin fix/stale-pending-replay-20261023
   gh pr create --base master --head fix/stale-pending-replay-20261023 \
     --title "fix(admission): settle archive-old pending candidates without screening" \
     --body "Pending body candidates published more than PENDING_REPLAY_MAX_AGE_DAYS (30) days ago are settled as stale_pending without a Jev call and no longer take the replay limit. Undated candidates and HTML link placeholders are unchanged. Doc: src/app/core/ingestion/pipeline.md. Gate: make lint + full pytest (paste results)."
   ```
   Use your real model name in Co-Authored-By, or drop the line.

## Report (all fields required)

- PR link; branch; commit SHA; `git diff --stat origin/master`.
- Output tail of each check in step 4.
- How stale rows are kept out of the replay limit.
- Deviations from this prompt and why; open questions, one line each (AGENTS.md "Owner And Questions").
