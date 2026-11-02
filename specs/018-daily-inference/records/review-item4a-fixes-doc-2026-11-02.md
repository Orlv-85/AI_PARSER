# Item 4a review fixes: feature document review

Reviewer: separate Codex agent session `storage_doc_review`, 2026-11-02.
Scope: review-fix edits to builder.md and bulletin_store.md against implementation and tests.
Review was read-only; the reviewer ran no tests or external calls.

No discrepancies found. Docs, code and tests agree on ordered article ids with None omitted,
session refresh after refusal, removal of replaced from logs, API storage failures returning 503,
and PostgreSQL test isolation. The writer packet stays unchanged because it selects fields
explicitly rather than serializing the full story.

Follow-up review: no discrepancies in the added successful-identity refresh rule, its retained
identity assertions, or the PostgreSQL SQL compiler test. Review remained read-only.

Handoff rule: save prompts before sharing them; feature prompts, reviews and reports belong in
specs/<NNN>-<name>/records/, never the docs/ root. Do not overwrite earlier prompts or reviews.
