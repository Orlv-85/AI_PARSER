# Prompt (Codex, gpt-6-astra high): spec 018 FR-022 review of bulletins 2026-11-09..14 (2026-11-15)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch
`docs/018-fr022-reviews-3`, from origin/master):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/fr022-review-3`.
You may read (never write) `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/fr022/`. Do not
commit, push or use gh. No network, no paid calls. Do not spawn sub-agents. Do not change code.

## Task (FR-022)

Same task, rubric and file format as the first two batches:
`specs/018-daily-inference/records/prompt-fr022-review-days-1-3-codex-2026-11-05.md` and
`records/prompt-fr022-review-days-4-7-codex-2026-11-09.md` (read both first), their outputs
`records/review-2026-11-02.md` .. `review-2026-11-08.md` and the summaries
`records/review-summary-2026-11-02..04.md`, `records/review-summary-2026-11-05..08.md`
(proposals F1.. and their ids).

Data: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/fr022/bulletins-2026-11-09..14.json`,
one key per day, same shape (`stored`, `packet_rebuilt_now`). The packet was built from the stored
stories' own links, so `packet_rebuilt_now.stories` are in the stored order (`s1..sN`:
`key_results`, rubric story, `cooperation`, incident story). Texts were read on 2026-11-15 from the
archive; they may differ slightly from what the model saw at 04:30 UTC. This is the last batch: it
closes the 14 days of FR-022.

What changed since batch 2 (check whether each works):
- All six days use `bulletin-writer-5` (release v0.1.162, 2026-11-09): a world story in another
  language never shows its original title (not in the story headline, the day headline or a gloss);
  such a story without a checked English headline and Telegram text is left out; words are
  attributed to whoever actually said them (the batch 2 finding on an invented speaker).

Extra points for this batch, in each day's review and in the summary:
- World stories (`origin: "world"`): is each one a concrete change in human life (FR-001, FR-014),
  or an explainer, opinion, forecast or press release? Is every published text in English?
- Fallback titles: any story whose published headline is the original `title` and not English
  (expected: none).
- Repeats: a story or event that already ran on the previous day (compare with the stored payload
  of the previous day; for 2026-11-09 compare with 2026-11-08 in
  `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/fr022/bulletins-2026-11-05..08.json`),
  even with a different URL and headline.
- Volume: the story count falls over the batch (5, 8, 5, 4, 4, 3) while
  `stored.numbers.writer.dropped` grows (27, 23, 27, 31, 43, 44 entries). From `stored.numbers`
  and the payload say what is dropped most (by reason and channel), whether the drops remove
  correct text, and whether a thin day still reads as a complete bulletin.
- For each open proposal of the two summaries: seen again (with the story), or not seen.

## Output

`specs/018-daily-inference/records/review-2026-11-09.md` .. `review-2026-11-14.md` (format of the
earlier batches), then `specs/018-daily-inference/records/review-summary-2026-11-09..14.md`: counts
per verdict per day, the writer-5 results, the world-story findings, fallback titles, repeats, the
volume finding, the fixes proposed across all three batches (deduplicated, ranked, old ids kept),
and the SC-002 verdict: is there any distorted ("wrong") story in the last 7 of the 14 days
(2026-11-08..14)? State it as yes/no with the stories.

Final message: files written; per day the verdict counts; the SC-002 verdict; the ranked fix list.
Be brief.
