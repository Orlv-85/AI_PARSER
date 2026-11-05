# Prompt (Codex, gpt-6-astra high): spec 018 FR-022 review of bulletins 2026-11-02..04 (2026-11-05)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch
`docs/018-fr022-reviews-1`, from origin/master):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/fr022-review-1`.
You may read (never write) `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/fr022/`. Do not
commit, push or use gh. No network, no paid calls. Do not spawn sub-agents. Do not change code.

## Task (FR-022)

Spec `specs/018-daily-inference/spec.md` FR-022: the grounding check catches invented names and
numbers, not distorted meaning; for the first 14 published days a separate session reviews each
bulletin against its sources (`records/review-<date>.md`); a wrong story leads to a rule or prompt
fix. Also read SC-002, `specs/018-daily-inference/voice.md`, the editorial rules ER-* in the spec,
and `src/app/core/bulletin/writer.md` (what the writer may and may not do).

Data: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/fr022/bulletins-2026-11-02..04.json`,
one key per day:
- `stored.payload`: the bulletin as published on the preview page (`Bulletin.as_dict()`): headline
  of the day, stories in `key_results`, `rubric_story`, `cooperation`, `incident_story`; per story
  `title` (article title), `headline`, `site_note`, `telegram_note`, `gloss`, `area`, `links`,
  `text_origin`; `stored.numbers.writer.dropped` lists sentences the checks dropped.
- `packet_rebuilt_now`: the source texts the writer was given, story by story in the same order
  (`s1..sN`, articles with outlet, title, text). Rebuilt on 2026-11-05 from stored data, so a text
  may differ slightly from what the model saw at 04:30 UTC that day; say so where it matters.

## For each day write `specs/018-daily-inference/records/review-<YYYY-MM-DD>.md`

Short and dry, English, ASCII:
1. Header: date, writer version (`stored.numbers.writer.version`), stories (model/title), dropped
   count.
2. Per story, one block: the published model text (headline, site sentences, telegram, gloss)
   checked against the story's source texts. Verdict per story: `ok` / `minor` / `wrong`.
   - `wrong`: a claim the sources do not support or contradict; meaning distorted (who did what,
     cause and effect, a claim of a company stated as fact, a possibility stated as done, wrong
     time, scope or number context); a headline that says more than the text; wrong attribution.
   - `minor`: imprecise or misleading emphasis, awkward or broken sentence, gloss that explains the
     wrong thing or a different entity, area label off, telegram that does not stand alone.
   - Quote the exact published sentence and the exact source passage for every `minor`/`wrong`.
3. Headline of the day: does it match the most important story and stay factual?
4. Selection sanity: is each story about AI changing the world as FR-001 intends (not a plain product
   launch dressed up)? One line per story only when doubtful.
5. Dropped sentences: from `dropped`, any pattern (for example many `too_close`) and whether the
   published text still reads as complete.
6. Findings that need a fix: each as `rule` or `prompt` with a one-line proposal. If none: "none".

Then `specs/018-daily-inference/records/review-summary-2026-11-02..04.md`: counts per verdict per
day, the fixes proposed across days (deduplicated, ranked), and whether SC-002 ("no story with
distorted meaning") holds so far.

## Report (your final message)

Files written; per day the verdict counts; the ranked fix list. Be brief.
