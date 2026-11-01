# Prompt: review of PR #195 (018 item 3, bulletin writer with grounding) (2026-11-01)

You review PR #195 (`feat/018-bulletin-writer`). You did not write it. **Read-only: no commits,
pushes, merges, PR comments, paid calls, network or production access.** Never run any command that
changes `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself (no `gh pr checkout`, no `git checkout`
there); you may read files there. Report in English.

## Read

- `gh pr view 195`, `gh pr diff 195`, `gh pr checks 195`.
- Implementer worktree (do not edit it): `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.claude/worktrees/agent-a6bc35051d90418ce`.
  For runs and mutations, create a worktree of `origin/feat/018-bulletin-writer` under your
  scratchpad named with `pr195`, run with `PYTHONPATH=<that worktree>/src` (venv1's editable
  install points at the main folder); never remove one you did not create; remove yours at the end.
- `AGENTS.md`; `specs/018-daily-inference/spec.md` (ER-1..ER-12, User Story 1 scenario 4, FR-005,
  FR-012) and `voice.md`; the item prompt `records/prompt-item3-writer-2026-11-01.md` (on the branch).
- Implementer report (judge each decision):
  `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/coord-records/specs/018-daily-inference/records/report-item3-writer-2026-11-01.md`.

## Check

1. **Production daily brief (most important).** `signals_brief.py` runs in production every night
   (02:00 digest). `grounding_error` was extracted from `_sentence`: is the brief's behavior exactly
   the same (same sentences kept and dropped, same logs, same cost path)? Compare old and new on the
   brief's tests and on a few hand inputs.
2. **Money.** Writer journal one file per UTC day, fixed $0.10 cap, `--max-usd` only lowers it; no
   call without `--write`; exit 2 without `DS_API_KEY`; "flash only": what happens if the
   configured model is not flash (refused, or mispriced)? Worst-case reservation vs the cap; the one
   transport retry reserved.
3. **Grounding**: numbers and names checked against the story's own texts; quote length (ER-9),
   copied runs, never-list, non-Latin letters; the transliteration helper; per-story grounding
   limits as stated. Find a sentence that passes but should not (an invented fact using only words
   and numbers present in the text) and say if it matters for the first days.
4. **Fallbacks**: invalid JSON, outage, cap -> title-only bulletin with a reason, never raises;
   story without passing sentences -> title (origin `title`); headline fallback to item 2's.
5. **Editorial rules in the prompt**: ER-1 (attribution), ER-2, ER-3 (no words in real people's
   mouths), ER-6 (framing adds no facts), ER-9 (own words, short quotes), ER-11, ER-12; the test
   pins them; `WRITER_VERSION`.
6. Archive text reading by canonical hash (ER-9: read, never published); text cut limit; FR-016
   import rules.
7. `render.py` and `builder.py` changes keep item 2's output when no model text exists (`--write`
   absent): same text as before.
8. Docs (`writer.md`, `builder.md`, `signals.md`) match code; rules name tests;
   `check_code_docs.py --diff origin/master --strict` (exit code).
9. **Mutation checks**: at least 12 (number check off, name check off, quote limit, copied-run
   length, never-list on model text, cap file key, run limit, no call without `--write`, fallback
   on invalid JSON, title fallback, headline fallback, brief `_sentence` path); table.
10. Run the writer tests, the signals brief tests, the builder tests, ruff on `src tests`.

## Report (final message)

Verdict (merge / merge after fixes / do not merge); findings by severity with file:line, the concrete
failure and a one-line fix; "must fix" separate from "nice to have"; reader-facing points listed
separately; mutation table; checks run.
