# Report: feed description in admission (2026-10-23)

Implementer report for `docs/prompt-feed-description-admission-2026-10-23.md`.
Branch `fix/feed-description-admission-20261023` off `origin/master` 5fa2a78.

## Files

- `src/app/core/jev.py`: `JevRelevanceScorer.state` returns `jev_state(article)` (title, summary,
  content) in daily mode when content is empty or whitespace; `jev_state` docstring updated.
- `src/app/core/ingestion/pipeline.md`: admission rule with its tests, Decisions row, Code map note.
- `tests/unit/test_jev.py`: mode `daily_feed_only` in `test_bounded_jev_text_is_pinned_per_mode`
  (helper `_pinned_row` shared with `daily_enrichment`); `test_daily_feed_only_candidate_sends_feed_description`.
- `tests/unit/test_daily_enrichment.py`: `test_feed_only_admission_is_reused_by_enrichment`.
- `docs/report-feed-description-admission-2026-10-23.md`: this report.

## Gate

- `ruff check src tests`: clean.
- `make lint` (ruff, mypy, pylint): mypy "no issues found in 192 source files", pylint 10.00/10.
- Full `pytest`: 1266 tests, 1264 passed, 0 failed, 2 skipped.
- `scripts/check_code_docs.py --diff origin/master --strict`: "code docs: 5 checked, ok".

## Pinned texts

- New: `daily_feed_only` = `a482cfc351a944e8a37803eb1cac3931ebdb8430d7d830b6b0e30e3272c130fe`
  (equal to `bounded_evidence` of the content-less article, so the cache key is unchanged).
- Unchanged: `admission`, `daily_enrichment`, `plain`, `admission_empty`.

## Facts vs. code

- Matched: `state()` used `jev_state(article, with_summary=not self.daily_enrichment_enabled)`;
  `_build_article_row` hashes title + content for the provenance; `bounded_evidence` keeps the summary.
- Deviation: the `jev_state` docstring became two lines (the one-line wording exceeded the
  100-character limit of ruff E501). Same words.
- `provider_response` in `test_daily_enrichment.py` asserts there is no `Summary:` in the state, so the
  new test has its own responder.

## Open questions

- None for the owner. After deploy: compare the unresolved share of new `openai_news` and
  `bullrich-dev-tldr-rss-ai-rss` candidates after 3 daily runs (report SQL).
