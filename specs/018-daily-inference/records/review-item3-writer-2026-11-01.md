# Review: PR #195, spec 018 item 3 bulletin writer (2026-11-01)

Reviewer: background agent (model sonnet), read-only, worktree at 4fe954b. Saved by the coordinator.

## Verdict: merge after fixes (none about money or the production brief)

- Production brief: `grounding_error` keeps order, regexes, `STARTERS`, `'s` strip; `canon=str`
  identity; same `BriefInvalid` codes; no logs or cost inside. Brief tests pass; mutation killed.
- Money: one journal per UTC day, $0.10 cap, `--max-usd` above cap rejected (nan, zero too); no
  call without `--write`; exit 2 without key; reservation about $0.023 for a 60 KB packet, retry
  reserved, worst case about $0.05; model a constant (flash). A failed call blocks further calls that
  UTC day (`unknown_or_failed_previous_call_requires_review`); identical reruns replay free.
- Fallbacks hold (invalid JSON, wrong model, finish reason, truncation, outage, cap, run limit,
  no stories); title and headline fallbacks hold.

## Must fix

1. Test that grounding is per story (a number or name from story A in story B is dropped); the
   "all-stories evidence" mutation survived.
2. `writer.md` overstates the check: name match is substring-based (`word.casefold() in names`:
   "Meta" passes on "metadata"; Arm, Intel, Art, calendar words Sun/Mar/Mon); spelled-out numbers
   and invented weekdays/months unchecked; straight single-quote quotes unchecked. Better: word-
   boundary name match for the writer (brief byte-identical).

## Nice to have

Pin `STORY_TEXT_MAX` with a literal (mutation 6000 -> 60000 survived); copy check also on headline
and gloss, or say not; pin "Never copy" and "every name and number must stand in the supplied text"
in the prompt test; `--max-usd` is a day-total limit (wording); document that a failed call blocks
the UTC day.

## Reader-facing

Never-list drops true sentences ("third-party tools"); wrong attribution or invented statements
with real names and numbers pass ("Mozilla said ..."): the first real days need a human read
(FR-022); fixture is hand-written, real quality unseen.

## Mutations

24 run, 22 killed; survived: `STORY_TEXT_MAX` 6000 -> 60000, per-story evidence -> all-stories.

## Checks

Writer tests and `-k "bulletin or brief or signals"` pass; ruff clean; `check_code_docs.py --strict`
exit 0 (12 docs).
