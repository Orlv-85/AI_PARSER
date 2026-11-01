# Prompt (Codex, gpt-6.1-sol high): fixes to PR #197 after review (2026-11-01)

Same directory and rules as `prompt-item2-outlet-name-codex-2026-11-01.md` (work only in
`/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/codex-outlet`; no commit, push, gh or network). Review: `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/coord-records/specs/018-daily-inference/records/review-item2-outlet-name-codex-2026-11-01.md`.

Decided by the coordinator:

1. Strip a trailing parenthesised label only when it names a feed: the label contains "feed",
   "newsletter" or "rss" (case-insensitive). "Machine Intelligence Research Institute (MIRI)" stays.
   Strip a leading `www.` case-insensitively.
2. If the result is empty, fall back to the article URL's hostname (without `www.`), then "source".
3. Tests first (see them fail, then pass): extend `test_outlet_name_drops_feed_label` with
   "(MIRI)" kept, "WWW.bbc.com" -> "bbc.com", label-only "(main feed)" -> ""; and in the existing
   loader test(s) seed a digest source named "TechCrunch (main feed)" (and a label-only source name
   if simple) and a world candidate with domain "www.news.example", and assert the loaded outlets
   are "TechCrunch" (hostname for the label-only one) and "news.example".
4. Update the rule in `src/app/core/bulletin/builder.md` to match (lines at most 100 characters).
5. Run the three checks of step 5 of the first prompt and fix failures.

Report: files changed, failing-test output, final check outputs with exit code.
