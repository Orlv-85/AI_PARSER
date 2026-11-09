# Review (Codex gpt-6-astra high): PR #219, writer F9 and F1 (2026-11-09)

Prompt: `prompt-writer-f9-f1-review-codex-2026-11-09.md`. Saved by the coordinator.

**Verdict: changes needed.**

- **P1 — Non-English day headline survives when its story is retained.** [writer.py:330](src/app/core/bulletin/writer.py:330) only clears headlines belonging to *removed* stories. If a German story gets a valid English story headline and Telegram note, but the model’s day headline fails, the builder’s German headline remains in storage, `/bulletin`, `/`, and Telegram. Clear non-English title-derived day headlines independently of story removal; add this regression case.

- **P2 — A copied foreign title can survive as a gloss.** [writer.py:317](src/app/core/bulletin/writer.py:317) retains a story with passing headline/Telegram text regardless of its gloss. A gloss such as the source title “Crosby bietet auf Weil Gotshal” passes existing checks: Latin script, grounded names, fewer than ten copied words. It is stored and rendered on both pages. This inherited validation gap remains exposed by F9; reject known foreign-title echoes and cover the gloss path.

**Minor notes:** Old payloads remain readable by pages, API and next-day deduplication. Dataclass-equality removal is safe here: equal stories necessarily share the removal predicate. `German` and `DEU` trigger filtering. Digest exemptions, incident counts and dropped IDs look correct. F1/version changes are correct; request contents otherwise remain unchanged, preserving same-version journal replay. Documentation matches the implemented rules but also preserves the headline gap above.

Permitted tests: **295 passed, 1 warning**. Existing tests miss both scenarios above. No edits or additional test commands.
Coordinator: both findings fixed by `prompt-writer-f9-f1-fixes-codex-2026-11-09.md`.
