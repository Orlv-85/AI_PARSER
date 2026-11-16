# Prompt: second review of the name-forms table (2026-11-16)

Fresh read-only reviewer: do not edit, commit or push. Worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-018-name-forms` (uncommitted; `git -C <wt> diff`,
untracked `src/app/core/bulletin/name_forms.json`). The first review and the fixes are at the end
of `specs/018-daily-inference/records/report-name-forms-2026-11-16.md`. Tests pass on this code: do
not rerun them; use the venv `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python` with
`PYTHONPATH=src` only to confirm a finding (`load_name_forms(NAME_FORMS_PATH)` gives the compiled
patterns; `fold(text).casefold()` is the evidence text they search).

Check only what is still open:
1. False passes left: for each form (all scripts; Latin after folding, Arabic word-bounded,
   Chinese/Japanese substring), a common word of Spanish, Portuguese, Italian, French, German,
   Russian, Ukrainian, Greek, Vietnamese, Arabic or Chinese text about AI that it matches but that
   does not mean the key. Only report collisions that are plausible in news text.
2. Whether the code fixes are right: inner `*` rejected, duplicate keys, Arabic word bounds, CJK
   substring, `fold` of đ/ß/ł/ø (and that Cyrillic and Greek folding is unchanged).

Final message: verdict (approve / fix needed) and findings (key, form, colliding word, fix), under
40 lines.
