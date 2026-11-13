# Review: PR #247 typed shapes instead of dict[str, Any]

Read-only review of `git diff origin/master...HEAD` in this worktree (branch
`refactor/typed-any-tail`). Do not edit, commit, push or use gh; no network; no sub-agents.

Intent: TypedDicts and `object` replace `dict[str, Any]` / `Any` in 8 modules; `Any` stays only on
provider request bodies. Behavior must not change, except: a phrase-library section of the wrong
type raises `PhraseError` (test `test_phrases_validation_messages`, rule in
`src/app/core/bulletin/builder.md`).

Check, in this order:
1. Runtime behavior changes hidden in the refactor. Focus on
   `src/app/storage/article_evidence_cache.py` (`_get` now returns `(meta, body)`; redirect history
   uses `response.copy()`; `_store_response` builds `StoredResponse`; evidence saved without `text`;
   robots cache), `src/app/ingest/date_evidence.py` (`_same_date`, JSON-LD loop),
   `src/app/usecases/archive/capture.py` (`_read_json`, `_extracted_page`), `src/app/web/period_view.py`
   (`_i`), `src/app/core/daily/signals_extract.py` (`_entity`, `_grounded_name`, `dataclasses.replace`),
   `src/app/usecases/sources/intake.py` (`_Row`, `IntakeJob`). Stored JSON files, report keys and
   reject reasons must stay the same.
2. Types that lie: a TypedDict key marked required that some path omits (or the reverse), a `cast`
   that is not backed by a check.
3. Missed `Any` that should have been typed in these 8 files.

Run only:
`PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python -m mypy`
`PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -p no:cacheprovider tests/unit/test_bulletin_builder.py -k phrases`

Report: findings ranked by severity, each with file:line, a concrete failing scenario and a fix;
then "no findings" for the areas that are clean. Keep it short.
