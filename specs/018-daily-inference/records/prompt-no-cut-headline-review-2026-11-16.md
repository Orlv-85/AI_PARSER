# Prompt: review of "no cut title headline" (2026-11-16)

Owner decision 2026-11-16: a builder title headline is never cut ("FACT CHECK TEAM*" on 2026-11-14
read as a broken line); no day headline is better. Change made by the coordinator in the worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-018-headline` (branch `fix/018-no-cut-headline`,
uncommitted; `git -C <worktree> diff`).

You are a fresh read-only reviewer: do not edit, commit or push. Tests were already run on this
code (bulletin, web, layer, monkeypatch, code-docs: pass; ruff clean; pylint 10.00): do not rerun
them; run a test only to confirm a specific finding.

Check:
1. `src/app/core/bulletin/builder.py` `_headline`/`build_bulletin`: a cut title is skipped, the next
   story can give the headline, `headline_cut` is false. Any caller left that expects a cut from
   the builder (`git grep -n "headline_cut\|make_headline\|marker" -- src`)? Is any code now dead
   for new builds (writer `_title_is_day_headline` cut branch, render footnote, phrases `cut`)?
   Stored older bulletins with `headline_cut` true must still render their footnote (web
   `bulletin_view.py`, `render.py`).
2. Tests in `tests/unit/test_bulletin_builder.py`: `test_title_needing_a_cut_is_not_a_headline`,
   `test_cut_headline_renders_the_footnote`, `test_make_headline_cuts_at_a_clause_boundary`: do they
   pin the rule?
3. `src/app/core/bulletin/builder.md` Headline rule and Decisions: true, short, no stale sentence
   (also grep `writer.md`, `src/app/web/pages.md` for text that says the builder cuts).

Final message: verdict (approve / fix needed), findings with file:line and a concrete case, under
30 lines.

## Review result (fresh Claude agent, Sonnet)
Approve, nothing to fix. Noted: for new builds the cut branch of writer `_title_is_day_headline`
and phrases `cut.marker` are no longer reached (the writer never runs on stored bulletins); left
in place, to be removed with the next writer change (decided 2026-11-16, coordinator).
