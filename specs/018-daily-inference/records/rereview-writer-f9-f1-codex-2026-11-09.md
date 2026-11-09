# Re-review (Codex gpt-6-astra high): PR #219 fixes (2026-11-09)

Prompt: `prompt-writer-f9-f1-rereview-codex-2026-11-09.md`. Saved by the coordinator.

**Verdict: changes needed.**

- **P2 — Model-returned foreign titles still pass.** [writer.py:356](src/app/core/bulletin/writer.py:356) checks title echoes only in glosses; line 334 exempts model day headlines. Concrete scenario: a `deu` story titled “Crosby bietet auf Weil Gotshal” receives that exact text as its model story headline or day headline, plus valid English Telegram text. The six-word title passes grounding and the ten-word copying threshold, so it survives for display. Extend foreign-title echo protection to these headline paths and add regression coverage.

Both requested fixes otherwise work through usable answers and `_fallback`; English/digest gloss exemptions and original dropped IDs are correct.

**Minor notes:** Added tests exercise the real checks without mocking validation, but miss the scenario above.

Permitted tests: **169 passed, 1 deprecation warning**. No edits or additional test runs.
Coordinator: fixed by the coordinator (small fix): the title-run check also drops a story headline (story then removed) and clears a model day headline that echo a known non-English title; tests `test_story_headline_echoing_non_english_title_is_removed`, `test_model_day_headline_echoing_non_english_title_is_cleared` (both failed first); CRAP 7/6/1.
