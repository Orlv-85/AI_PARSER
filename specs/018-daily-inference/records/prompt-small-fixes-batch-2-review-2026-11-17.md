# Prompt: review of spec 018 small fixes, batch 2 (2026-11-17)

Fresh read-only reviewer: do not edit, commit or push. Worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-018-small-2` (uncommitted; `git -C <wt> diff`). Task:
`specs/018-daily-inference/records/prompt-small-fixes-batch-2-2026-11-17.md`; report:
`report-small-fixes-batch-2-2026-11-17.md` (same folder). Tests pass on this code: do not rerun
them; run a check only to confirm a finding (venv
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`, `PYTHONPATH=src`).

Check: (1) `repeats.py` `_conflicted`/`_apply`: any case where a true repeat of a published story
is now kept, or a wrong one dropped; summary `kept` reasons; prompt text. (2) `_camel_error`:
false drops of ordinary words ("mRNA", "kWh", "iOS", "eBay" in evidence), possessives, words with
digits. (3) The removed cut branch and the deleted test: anything still needing it? (4) Docs
`repeats.md`, `writer.md`: true, short, test names exist.

Final message: verdict and findings (file:line, case, fix), under 30 lines.
