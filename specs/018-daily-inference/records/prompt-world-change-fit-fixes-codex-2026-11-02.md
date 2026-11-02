# Prompt (Codex fix, gpt-6.1-sol high, resumed session): world_change fit, review fixes (2026-11-02)

Same worktree and rules as before (`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/world-change-fit`;
no commit, push, gh or network). The review (Astra) found nothing blocking; make these three changes,
tests first, smallest code.

1. Doc gap (P3). With empty content the state is title + summary (summary fallback), and only the
   content is cut, so such a request can still exceed the bound (title "ж"*1024 + summary "ж"*4000:
   35344 bytes with the allowance). Do not cut the summary. In `world_change.md` (Request rule you
   added) state the exception: "a request that still does not fit with empty content (a long
   non-ASCII title or summary fallback) is sent uncut and fails as `JevInputTooLarge`". Add test
   `test_summary_fallback_too_large_is_sent_uncut` (body equals the uncut body) and name it in the rule.
2. Surviving mutant (default content limit lowered to 15999 not caught). Add test
   `test_fitting_full_length_ascii_content_is_unchanged`: ASCII content of exactly `CONTENT_LIMIT`
   characters (plus extra characters beyond it), body fits, and `body(article)["state"] ==
   world_change_state(article)` and the content part has exactly `CONTENT_LIMIT` characters. Name it
   in the doc rule.
3. Log context for the world stream. `world_screen._assess` passes `WorldItem` with `id=None` (do not
   change that: `id` is the article id). In `assess`, add `"url_canonical_hash"` to the failure/stop
   context when the object has a non-empty one (keep `article_id` when present). Update
   `test_failure_log_names_the_article` (or add a case) and the doc rule ("carries the article id
   and/or `url_canonical_hash`").

Then run the same step 6 checks as in the first prompt (scoped tests, full suite with `-n auto`,
`PYTHONPATH=src make lint ...`, `check_code_docs.py --diff origin/master --strict` alone and last).

Report: files changed, one line each; failing-test output before the code; check outputs (last
lines, exit codes).
