# Report: spec 018 small fixes, batch 2 (2026-11-17)

Implementer: background Claude agent (Sonnet), prompt `prompt-small-fixes-batch-2-2026-11-17.md`;
saved by the coordinator from the agent's final message, shortened.

## Fix 1, repeats: today's duplicates are not repeats
- Diagnosis (coordinator, prod journal replay of 2026-11-16): five articles of the Korean exam
  story were grouped in `same_event`; four of them were also listed in `repeats` against p1
  (Systematix), c2 was not. Same shape on 2026-11-15.
- `REPEATS_VERSION` `bulletin-repeats-2`; the prompt says duplicates of today go only in
  `same_event`. `_conflicted`: a repeat pair whose candidate is in a group with a non-repeated
  member is kept as `same_event_conflict` (`_kept_reason`; `_merge` split out of `_apply`).
- Tests: `test_prompt_says_duplicates_of_today_are_not_repeats` (failed first on version/prompt),
  `test_repeat_inside_a_partly_repeated_group_is_kept` (the coordinator removed the guard: the
  test fails), `test_fully_repeated_group_is_dropped`; `test_dropped_member_is_not_merged`
  rewritten to a fully repeated group (old case is now kept by rule).

## Fix 2, lower-case-first names
- `CAMEL_NAME`, `_camel_error` after `grounding_error` in `_evidence_error` (shared
  `grounding_error` untouched). Tests: `test_camel_case_name_needs_the_text` (failed first: None),
  `test_lower_case_words_are_not_names`.

## Fix 3, dead cut branch of the writer
- `_title_is_day_headline` is equality only; cut cases removed from
  `test_bulletin_writer_language.py`, `test_removed_title_prefix_does_not_clear_another_cut_headline`
  deleted with its doc sentence. Pure removal, tests pass before and after.

## Checks
- Scoped pytest (bulletin, web, layer, monkeypatch, code-docs) rc=0; ruff clean; pylint 10.00;
  crapper with coverage: changed functions under 10 (`_apply` 11 -> under 10), untouched
  `_repeat_pairs` 10.0; dryer none.

## Review (fresh Claude agent, Sonnet, `prompt-small-fixes-batch-2-review-2026-11-17.md`)
Approve, no fixes required. Noted and taken: `repeats.md` Decisions now says the guard also keeps a
true repeat when the model forgets a group member. Noted, left: `_camel_error` drops "mRNA" when
the source writes "messenger RNA" (same strictness as other names); an old cut bulletin re-run
through the writer is not reachable.
