# Prompt (Codex, gpt-6-astra high): spec 018 FR-022 review of bulletins 2026-11-05..08 (2026-11-09)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch
`docs/018-fr022-reviews-2`, from origin/master):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/fr022-review-2`.
You may read (never write) `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/fr022/`. Do not
commit, push or use gh. No network, no paid calls. Do not spawn sub-agents. Do not change code.

## Task (FR-022)

Same task, rubric and file format as the first batch:
`specs/018-daily-inference/records/prompt-fr022-review-days-1-3-codex-2026-11-05.md` (read it first),
and its outputs `records/review-2026-11-02.md` .. `review-2026-11-04.md` and
`records/review-summary-2026-11-02..04.md` (proposals F1..F8).

Data: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/fr022/bulletins-2026-11-05..08.json`,
one key per day, same shape (`stored`, `packet_rebuilt_now`). This time the packet was built from
the stored stories' own links, so `packet_rebuilt_now.stories` are in the stored order (`s1..sN`:
`key_results`, rubric story, `cooperation`, incident story). Texts were read on 2026-11-09 from the
archive; they may differ slightly from what the model saw at 04:30 UTC.

What changed since batch 1 (check whether each works):
- All four days use `bulletin-writer-4`: headlines attribute a company's claimed results (F1) and
  keep the qualifiers that limit a claim (F2).
- From 2026-11-06 the bulletin also takes world stream stories (`origin: "world"`): general news
  outlets in any language about AI in human life (FR-014..FR-018). A world story already shown the
  day before (same URL or title key) is left out.

Extra points for this batch, in each day's review and in the summary:
- World stories: is each one a concrete change in human life (FR-001, FR-014), or an explainer,
  opinion, forecast or press release? Is the published text in English?
- Fallback titles: list every story whose published headline is the original `title` (no model
  headline) and whose title is not English (seen: German on 11-06, Chinese and Danish on 11-07).
- Repeats: a story or event that already ran on the previous day (compare with the stored payload
  of the previous day; for 2026-11-05 compare with 2026-11-04 in
  `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/fr022/bulletins-2026-11-02..04.json`),
  even with a different URL and headline (seen: Google and AI in schools on 11-05 and 11-06).
- For each of F3..F8 of the first summary: seen again (with the story), or not seen.

## Output

`specs/018-daily-inference/records/review-2026-11-05.md` .. `review-2026-11-08.md` (format of batch
1), then `specs/018-daily-inference/records/review-summary-2026-11-05..08.md`: counts per verdict per
day, results of F1/F2, the world-story findings, fallback titles, repeats, the fixes proposed
across both batches (deduplicated, ranked, old ids kept, new ids from F9), and whether SC-002 holds
so far.

Final message: files written; per day the verdict counts; the ranked fix list. Be brief.
