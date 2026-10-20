# Verification fixes for the 006 implementer (2026-10-19)

Source: `specs/006-daily-ai-signals/records/daily-ai-signals-pr39-fix-verification-gpt6-2026-10-19.md` (reviewed head `1d7904c`).
Everything else in the fix pass is verified as fixed. Phase 7 after the F19 decision: displayed New
34/0/6 (85% OK, 0% BAD), recall 34/42.

Fix now (test-first; the report names a failing test for each - reuse its scenario):

| ID | Item | Direction |
| --- | --- | --- |
| V01 | F19 cleans digest text with `clean()`, which drops parentheses, so "(preview)", "(early access)" are lost before the not-released check; the payload snippet loses them too. | Run the NOT_RELEASED check and build the snippet on the raw digest text; use separate normalization only for name matching. |
| V02 | F19 suppresses single-token names without a vendor, or with any shared vendor word ("Beam search ..." suppresses a new model Beam; generic word "labs" counts as vendor). | Single-token names without digits: suppress only with an identified vendor whose normalized name (or alias) occurs in the same digest item; no vendor -> no lexical suppression for single tokens. |
| V03 | F20 joins `OpenAI` with an unrelated `Open` vendor (glued-suffix form). | Join glued spellings only when a spaced spelling with the separate company suffix exists in evidence (e.g. "Liquid AI"), or via the alias table; negative collision test. |
| V04 | F21 plural folding changes base keys of old mentions, so a stored merge/alias selector stops matching when the singular appears later. | Resolve stored source/target base selectors through the current plural equivalence, the same way F4 resolves vendor classes, including conflict detection; test late singular for source and target. |

Defer (record in plan.md "Deferred" with its trigger; no code now):

| ID | Item | Trigger |
| --- | --- | --- |
| V05 | After retention deletes `article_signals`, an empty newer extraction no longer hides older-version mentions (F10 remainder). Latent: needs a second `EXTRACTION_VERSION`. | Before adding a second extraction version: persist the selected version / empty result outside the cascaded table. |

Then: full gate (clean copy, PostgreSQL), `--recompute-only` re-measure ($0) with the T7.2 checklist,
update `dry-run.md`, PR description and plan, push, CI green, stop and reply with the head SHA and a
finding -> commit/test table. The coordinator verifies this small diff directly; no further external
review round unless the coordinator finds a major issue.
