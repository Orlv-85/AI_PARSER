# Prompt: fix PR #39 review findings (006 implementer, 2026-10-19)

Four independent reviews of PR #39 (head `8f30549`) are consolidated by the coordinator in
`docs/daily-ai-signals-pr39-review-consolidated-2026-10-19.md`. All verdicts: merge after fixes.

Order:

1. If Phase 7 is still running, finish it and report it first (unchanged rules). No code changes
   before the Phase 7 report.
2. Fix F1-F17 from the consolidated file, test-first: each finding gets a regression test that fails
   on `8f30549` and passes after the fix. The four source reports contain reproductions and file:line
   references; read them for details. N1-N3 only if trivial; otherwise list them as follow-ups in
   plan.md.
3. Constraints: no change to the global SQLite pragma in `storage/db.py` (F9 is fixed by identity
   keying); no compose change for F14 (docs only); keep `scripts/run_daily_digest_job.sh` behaviour
   otherwise identical; no paid provider calls.
4. Commit in groups (identity/overrides F2-F4,F13; storage/version/identity F9,F10; run/retry/backfill
   F1,F11,F12; extraction F7,F8; web/UI F5,F16,N1; job/docs F6,F14,F15,F17,N2,N3). Commit the
   coordinator files `docs/daily-ai-signals-pr39-review-*.md`,
   `docs/daily-ai-signals-pr39-review-consolidated-2026-10-19.md` and this prompt in a separate
   docs commit.
5. Full gate in a clean copy with PostgreSQL as in CI (`make lint`, full pytest, `bash -n`); push;
   CI green.
6. Re-measure Phase 7 with `--recompute-only` on the scratch DB ($0) and update `dry-run.md`
   (displayed and uncapped New precision, recall, stories).
7. Update the PR description (rollback order from F6, list of fixes) and stop. Reply with: new head
   SHA, finding -> commit/test table, gate results, Phase 7 numbers before/after, anything not fixed
   and why.

## Addendum after the Phase 7 report (a9e0cdf)

Coordinator checked production (read-only, 2026-10-19): of 1,695 legacy history digest items
(2026-08-03..10-09) 1,642 match an article; only 443 have content >= 300 chars, but **1,009 of the rest
have a real RSS `Article.summary` >= 100 chars** (median 290, no "Source: ..." placeholders). All 377
comparable items (10-10..10-16) have full text. So the title-only history is the same on production,
and most of it can be fixed with text we already store.

Add these findings to the fix pass (same rules: test-first, grouped commits):

| ID | Severity | Item | Fix direction |
| --- | --- | --- | --- |
| F18 | major | Title-only history articles produce empty extractions and count as processed, so first_seen misses real history (Surface Laptop Ultra #1 New on 10-16). | Extraction input fallback: when content < 300 chars, use `Title + Summary (Article.summary, cleaned, capped)` instead of the title alone; grounding against that same text. This changes the content hash only for those articles, so they re-extract (budget below). Record the input kind (`full`, `title_summary`, `title_only`) per extraction. |
| F19 | major | No safety net for New when history evidence is thin. | Deterministic New suppression: an entity is not New on D if its display/canonical name (normalized, multi-token or digit-bearing, or exact-case single token with vendor co-occurrence - the gate's rule) occurs in the title or summary of any in-scope article before D. Pure, cached per recompute, no provider calls; record suppressed items and the matching day in the payload for debugging. |
| F20 | minor | Vendor spellings `LiquidAI` vs `Liquid AI` form different vendor classes (new size of LFM2.5 not seen as a variant). | Vendor equivalence also on the space-free join of tokens, with the company-suffix rule applied to the joined form when the remainder >= 3 chars; test LiquidAI/Liquid AI, OpenAI must not become "open". |
| F21 | minor | `Gemini Agents` vs `Gemini agent` are different entities. | Treat a trailing plural `s` on the last token as the same base key only when the singular form also occurs in evidence for the same type group; test that unrelated names ending in `s` do not merge. |
| F22 | minor | All-lowercase generic feature names (`dynamic workflows`, `on-demand capacity mode`) reach New. | New eligibility requires a proper-name shape: at least one uppercase letter or digit, or a single hyphen/dot-joined token (keeps `agent-engineer`, `d1-ultra`); such entities still count for stories and spikes. |

Answers to the Phase 7 questions:

1. Title-only/summary-less articles count as processed for the 90% day coverage (they were attempted;
   coverage measures the pipeline, not source richness). Add one paragraph to `docs/daily-signals.md`
   explaining input kinds and that legacy history is thinner. Legacy days are history-only anyway.
2. Yes, fix Phase 7 findings 2-4 now (F20-F22), together with F18-F19.
3. Top-story membership 89% strict / 98% lenient is accepted for this release; the gap is one known
   SEO-comparison cluster (single SEO publisher). Record a follow-up: down-weight or exclude
   SEO/comparison pages per source (source quality, not clustering).

Budget: F18 re-extracts about 1,000 history articles. Approved from the remaining validation budget
($1.1734): hard stop `--max-usd 1.10` total for this re-extraction on the scratch DB. Never on
production. Then re-measure everything with `--recompute-only` and report displayed and uncapped New
precision, recall, and the T7.2 checklist before/after.

Also commit the coordinator file `docs/jev-novelty-second-opinion-todo.json` (backlog, no code) in the
docs commit.
