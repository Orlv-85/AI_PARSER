# Prompt: coordinator, next session (2026-10-20)

You continue as the **coordinator** for `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. The owner
writes in Russian; answer in Russian, short.

1. Read `AGENTS.md`, your memory files and `docs/coordinator-state-2026-10-20.json` (rules, state,
   next steps). Nothing else up front.
2. Report the state in three or four lines. Repeat the open owner question (P2: close the `Fetcher`
   and sort `/admin` by date, recommended yes).
3. Start P1: write the prompt for a separate session (tests for the rules marked "no test" in
   `src/app/core/pipeline.md`, tests only) to `docs/prompt-pipeline-tests-<date>.md`, give the owner
   the link. Review its PR against the doc, merge when CI is green.
4. Then P3 (refactor) the same way, after P1 is merged. Write the next prompt only after reviewing
   the previous PR.
