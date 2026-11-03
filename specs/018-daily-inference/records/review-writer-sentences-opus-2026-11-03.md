# Second review: writer paragraph split, quote fix and title cleanup (2026-11-03)

Reviewer: a fresh Claude Opus agent, read-only. Coordinator applied the fixes.

1. Quote pairing: the splitter knew only `"` and U+201C as openers, while the quote check folds
   U+201C, U+201D and U+201E to `"`. `OpenAI said ”We won. They lost.”` split and passed.
   Fixed: an open quote is an odd count of `"` after the same folding; tests in
   `test_splitter_quote_edges` (U+201D and German low quotes).
2. Copy run across a sentence boundary is not caught after splitting. Not changed: the copy check
   stays per sentence, as for one-sentence list items (the intended answer shape); a
   cross-boundary check also flagged close paraphrases of adjacent good sentences. Recorded as a
   decision in `writer.md`.
3. `digest_title` import from `app.core.daily.enrichment` costs ~100 ms at import; no cycle. Left.
