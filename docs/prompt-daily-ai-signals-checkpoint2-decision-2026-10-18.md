# Checkpoint 2 decision for the 006 implementer (2026-10-18)

Coordinator review of phases 0-3 (commits 44d78d2, 8e823d2, b4d68f3): accepted. The full suite was
re-run by the coordinator in a clean copy without `.env` (per `docs/troubleshooting.md`): green.

Answers:

1. Deviations 1-3 are confirmed (vendor split only for vendors seen as `org`; recovery suffix on
   `--retry-skipped`; Pluto pinned in its real form without first-word matching).
2. Keep the 13 `too-many-instance-attributes` suppressions on data records; do not change the global
   pylint config.
3. Continue with phases 4-6 (API, main-page UI, job script, compose line, docs) and open the PR to
   `master` (do not merge). Stop at checkpoint 3.

Additions for this stage:

- The hidden-BAD caveat (Blueprints AI, Maka, "on-demand capacity mode" still New below the cap of 8)
  stays open. In Phase 7 report precision for both the displayed list and the full uncapped New list;
  no extra prompt runs now.
- At checkpoint 3 include rendered screenshots (or saved HTML) of `/` for ready, partial,
  building_history/spikes-only and unavailable states, desktop and mobile width, and the exact local
  commands used (explicit env, no runtime default changes).
- In the PR description list every production-sensitive change (job script, compose line, settings,
  migration) with its rollback step.
