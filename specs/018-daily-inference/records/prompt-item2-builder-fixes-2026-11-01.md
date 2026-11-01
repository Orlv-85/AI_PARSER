# Prompt: fixes to PR #192 after review (018 item 2) (2026-11-01)

Continue on `feat/018-bulletin-builder` in your worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.claude/worktrees/agent-a9819038b5910c0e5`. Same rules
as `prompt-item2-builder-2026-11-01.md` (no paid calls, no main-folder changes, doc first, test
first). Review: `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/coord-records/specs/018-daily-inference/records/review-item2-builder-2026-11-01.md`.
If `origin/master` moved (W7 PR #193 may merge), rebase and resolve.

Decided by the coordinator (the bulletin is only on a preview page until the owner's 14-day review,
so these are tuned later; write each "why" in `builder.md` Decisions as "decided 2026-11-01
(agent): ..."):

1. Headline: no cut at a comma. Cut only after `:` or `;`, before a dash, or before
   but/while/because/although; a story without such a boundary is skipped; none fits -> no headline
   line (item 3 writes headlines). Update the test and the doc; say in the doc that the headline may
   then not be the top story.
2. Busy-day median only over ready days; test with a partial day in the window.
3. Reactions must imply no fact (`voice.md`). Remove from `phrases.json` the area reactions that
   claim an outcome: Work ("The transition of professions continues.", "Productivity grows."),
   Money, Infrastructure, Science/Health. Keep "The Administration welcomes the dialogue." (Faith,
   Culture) and the limit and AI-actor reactions. Edit `voice.md` the same way with one line why.
   The owner is told in the coordinator's reply.
4. Event representative chosen among non-`none` members first (a strong `none` no longer drops an
   `added` story); test.
5. State in `builder.md` that harm stories counted in incidents are those shown-eligible (answer not
   `none`, above threshold); no code change.
6. Dedup: match hash-fallback digest articles to the top-story key by canonical hash too; test.
7. Log the assessed share of the day's digest articles (`bulletin_assessed_share` or in the skip/
   build log line); in `--json` add the counts.
8. `voice.md`: half a line on the 7-stored-days minimum for busy.
9. Numbers line: add a second variant to each of the two lines (plain, factual, no new claim) so it
   varies by date; test.
10. Close survivors: M18 (`issue` never in Key results), M22 (plain line never an AI-actor issue),
    M26 (median window excludes the day itself). Show each new test fails on its mutation.

Checks as before (ruff, scoped tests, `make lint`, full pytest, `check_code_docs.py --strict` run
alone after the last commit, report the exit code). Push to the same branch, update the PR body
(new fixture bulletin). Copy this prompt into `specs/018-daily-inference/records/`. Report: commits,
items, mutation results, checks with counts, the new fixture bulletin text.
