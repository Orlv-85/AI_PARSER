# F19 decision for the 006 implementer (2026-10-19)

Coordinator review of the fix pass (head 216d9f1): accepted. Remaining item: F19 text source.

Facts from `dry-run.md` section 9: F18 alone now removes Surface Laptop Ultra (the case F19 was added
for). F19 as implemented suppresses two items wrongly: Muse Spark Open (a 09-03 RSS summary mentions
a roadmap "open weights release") and Code Review for Claude Code (an earlier research preview; GA
after preview is New per OD1). A lexical hit means "mentioned before", not "released before".

Decision:

1. F19 text source = **digest item titles and summaries only** (what we published), not article RSS
   summaries; history window = the digest history present in the DB (production digests start
   2026-08-03).
2. Ignore a lexical hit when the earlier matching text frames the entity as not yet released:
   case-insensitive words `preview`, `beta`, `alpha`, `waitlist`, `early access`, `roadmap`, `plans to`,
   `will release`, `will launch`, `coming soon`, `upcoming`. This keeps OD1 (GA after preview is New).
   Keep the list as a constant next to the rule, with tests for both kinds of hits.
3. Keep recording suppressed items (entity, matched day, matched text snippet) in the payload so false
   suppressions are visible in production.
4. Re-measure with `--recompute-only` ($0): report displayed/uncapped precision, recall and the T7.2
   checklist (Muse Spark Open must be New on 10-15). Update `dry-run.md` and the plan text for F19.
5. Full gate (clean copy, PostgreSQL), push, CI green, update the PR description, then stop and reply
   with the new head SHA. A verification review of the fix diff runs after that.
