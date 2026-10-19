# Checkpoint 1 decision for the 006 implementer (2026-10-18)

Owner + coordinator decision on `.specify/specs/006-daily-ai-signals/prompt-gate.md`:

**Option A accepted.** Freeze `daily-signals-extract-5` as the production prompt (with the revision-1
structure sentence). No further paid prompt runs in this phase. Continue with B2 (Phases 0-3, then stop
at checkpoint 2), and add these as Phase 1 tasks, test first, no provider calls:

1. Finding 3 - deterministic retrospective check in validation: `is_new = false` when the quote dates the
   release before the article (explicit month/day earlier than the publication month, "earlier this
   year", "last year", "last month", "in late/early <month>", "we introduced" in a year-review context
   if it can be done without false positives). Pin Qwen 3.8-27B (10-14) and AlphaProtein Novo (10-13)
   from the gate data as fixtures; keep Glimpse, Clef-omni, Helix World passing.
2. Finding 4 - quote check also accepts the entity's base name (vendor-stripped, Decision 2) and the
   canonical name. Pin "Reflection AI introduced Beam" and "Pluto, fresh out of stealth".
3. Finding 5 - vendor-prefix stripping only for vendor classes that also occur as `org` entities in the
   evidence, and never leave a base remainder that starts with a digit. Pin "Gemini 4 Argon" ->
   base key keeps "gemini".
4. Finding 6 - New ordering: confirmed first; then early items by type order model, hardware,
   benchmark, dataset, technology, company, product, policy; then publishers, articles, name. Products
   stay eligible (no OD1 change).
5. Update plan Decision 1 (v5 text), Decision 2, Decision 5 and the Phase 7 acceptance bar:
   displayed New over 2026-10-12..16 with cached v5 responses and the fixes above: OK >= 75%,
   BAD <= 10%, no non-AI / generic / established-company items; record the re-measured numbers in
   `prompt-gate.md` ("After code fixes") before checkpoint 2 - this re-run uses the cache only ($0).

Commit the plan/tasks update first, then follow tasks.md. Stop at checkpoint 2 as the Phase B prompt
says. Remaining validation budget: $1.818 (Phase 7 only).
