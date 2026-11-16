# Prompt: third, narrow review of the name forms (2026-11-16)

Fresh read-only reviewer: do not edit, commit or push. Worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-018-name-forms`. Review 2 and the fixes are the last
section of `specs/018-daily-inference/records/report-name-forms-2026-11-16.md`. Tests pass on
this code: do not rerun them; use `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`
with `PYTHONPATH=src` and `sentence_error` only to confirm a finding.

Check only:
1. `_name_words(raw, text)` in `src/app/core/bulletin/writer_grounding.py`: can two plain words
   still join into an invented name? Is a Vietnamese/accented pair handled (fold of the joined
   pair)? Any case where raw tokens and folded text disagree badly (Cyrillic, Greek, CJK)?
2. The replaced forms listed in that section (look them up in `name_forms.json`): is any
   replacement itself a new collision, or wrong for its key?

Do not re-scan the whole table. Final message: verdict and findings, under 25 lines.
