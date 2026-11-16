# Prompt: review of the name-forms table (2026-11-16)

Fresh read-only reviewer: do not edit, commit or push. Worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-018-name-forms` (uncommitted; `git -C <wt> diff` and
the untracked `src/app/core/bulletin/name_forms.json`). Task: `prompt-name-forms-2026-11-16.md`;
report: `report-name-forms-2026-11-16.md` (same records folder). Tests were run on this code: do
not rerun them; run a check only to confirm a finding (`PYTHONPATH=src`, venv
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`).

Check:
1. False passes, the main risk. For every Latin form after folding (`fold(form).casefold()`),
   prefix forms most of all, find common English, Spanish, Italian, Portuguese, French, German or
   Vietnamese words it matches at a word start that do not mean the key (like "gree*" -> "green",
   "Γαλλ*" folds to "gall" -> "gallery"). Remember Cyrillic and Greek forms are folded to Latin
   too. Also substring forms in Chinese/Arabic that are parts of unrelated words. List each with
   the colliding word.
2. Wrong forms (a form that does not mean the key) and generic keys that let an invented name
   pass (`united`, `states`, `union`, `court`, `university`, `bank`, `may`, `march`).
3. Code: `_form_pattern`, `load_name_forms`, `_name_words`, `fold` (Greek after accent removal;
   Cyrillic unchanged), the joined-token pairs (can they ground an invented name?), caching.
4. `writer.md`: Grounding check 5 and Decisions true and short; test names exist.

Final message: verdict, then findings (file:line or the JSON key/form, the concrete colliding
word or case, a fix), under 50 lines.
