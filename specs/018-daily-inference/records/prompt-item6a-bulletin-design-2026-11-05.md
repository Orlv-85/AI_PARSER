# Prompt (separate design session): spec 018 item 6a, design of the bulletin page (2026-11-05)

Repo `ai-news-collector` (`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`). You are the design session
of owner decision Q1 of spec 018 (The Daily Inference). The owner talks Russian, short and plain,
takes part minimally and never reads repo files; ask the owner only about the look (what readers
see), one yes/no with a recommendation. All other choices you make yourself and list in your report.

## Setup and limits

- Work only in a new git worktree: `git worktree add docs/work/worktrees/item6a-bulletin-design -b
  feat/018-item6a-bulletin-design origin/master` (run from the repo root after `git fetch`). Do not
  touch the main folder, except reading the sample data below.
- Do not commit, push or run any `gh` command; the coordinator session commits, opens the PR, has a
  different model review it and merges.
- No paid calls, no production access, no sub-agents for review.
- Read first: `AGENTS.md`; `specs/018-daily-inference/spec.md` (Q1, Q2, User Story 2, FR-009,
  FR-010, FR-019); `specs/018-daily-inference/voice.md` ("Structure of an issue", "Areas", samples);
  `src/app/web/pages.md` ("Hidden bulletin preview"); `src/app/web/bulletin_view.py`,
  `src/app/web/bulletin.html`, `src/app/web/routes/bulletin.py`; `src/app/storage/bulletin_store.md`
  (payload fields); their tests (`rg -l "bulletin_page" tests`).
- Sample data, real stored rows of 2026-11-02..04 (git-ignored, do not copy into git):
  `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/fr022/bulletins-2026-11-02..04.json`,
  key `<date>.stored` (`status`, `payload`, `numbers`). Ignore `packet_rebuilt_now` (third-party
  article texts). For local rendering put rows into a scratch SQLite DB through `BulletinRepo`, or
  build test fixtures from the payload shape with invented text.

## Scope: 6a only

Item 6 is split. **6a (you)**: the look of the bulletin, applied to the existing hidden preview page
`GET /bulletin?date=`. **6b (later, another executor)**: `/` serves the bulletin behind the
`bulletin_home_page` switch, the digest moves to `/daily`, page counter FR-023. So in 6a:
`/`, routes, URLs, switches, storage and APIs stay unchanged; `/bulletin` stays public, unlinked and
`noindex, nofollow`; every rule of `pages.md` "Hidden bulletin preview" still holds (escaping,
http/https-only links, 400/404/503 pages, previous/next links).

## What the page must be (Q1, Q2, voice.md)

- Looks like an official bulletin, made modern and mobile-first: masthead `THE DAILY INFERENCE`,
  the stored `byline` (with "Day N"), serif type, columns on wide screens, one column on a phone.
  Phone first: check 360 px and 390 px wide (no horizontal scroll, readable size, tap targets),
  then tablet and desktop.
- The whole issue in the order of voice.md "Structure of an issue", from the stored payload:
  headline of the day, opening, numbers line, Key results, the positive rubric (when present),
  Cooperation with humanity, Isolated incidents: N with the "Among them" story, closing, then
  "Full report (N) →". Empty sections left out. Per story: `headline` if set, else `title`; site
  note sentences; gloss; area label; outlet names linked to sources.
- "Full report (N) →" links to `/?date=D` while the digest still lives at `/` (6b changes it to the
  stored `full_report_url`, `/daily?date=D`). Same for the skipped-day digest link (unchanged).
- Footer: "Satire. Every fact is real and linked." (FR-010, Q2) and "News discovery: GDELT Project"
  linked to https://www.gdeltproject.org/ (owner decision 2026-10-31).
- Checking data of the preview (`text_origin`, `origin`, stored `numbers`) stays on the page but out
  of the reader's way: one collapsed `<details>` block "For checking" at the bottom. 6b will not show
  it on `/`.
- Skipped, missing, error and empty-store pages get the same masthead and footer.
- Fonts: system serif and sans stacks, no web-font or other third-party requests (no cookies, no
  tracking; decided 2026-11-05 (agent): nothing external on a public page). Light and dark
  (`prefers-color-scheme`) both readable. Print is not required.
- Own stylesheet `src/app/web/static/css/bulletin.css` (not under `static/admin/`); do not change
  `digest.css` or any other page's look.

## Steps (doc first, then failing tests, then code)

1. Doc: update `src/app/web/pages.md` "Hidden bulletin preview": Behavior rules for the issue
   structure, footer, checking block and phone layout, each with its test names; Decisions (look per
   Q1; system fonts; `/?date=` until 6b; checking block); Code map rows for `bulletin.css`.
2. Failing tests first (run them, see each fail for the expected reason), at least:
   `test_bulletin_page_issue_order` (sections in voice.md order, empty ones left out),
   `test_bulletin_page_masthead_and_byline`, `test_bulletin_page_footer_satire_and_gdelt`,
   `test_bulletin_page_full_report_links_digest`, `test_bulletin_page_checking_block_collapsed`,
   `test_bulletin_page_status_pages_share_shell`, `test_bulletin_page_mobile_viewport`
   (viewport meta and the stylesheet link). Keep every existing `test_bulletin_page_*` green.
3. Code: `bulletin_view.py`, `bulletin.html`, `bulletin.css`. Keep the HTML small and semantic
   (`header`, `article`, `section`, `footer`); no JavaScript unless a reason is written in Decisions.
4. Look: run the app locally on a scratch SQLite DB with the three sample days (explicit env
   settings, do not change runtime defaults; `./run_web.sh` or uvicorn on port 8010), take
   screenshots at 390 px and 1280 px of 2026-11-04 and of a skipped day, and save them under
   `/private/tmp/` (not in git). Show them to the owner as one private Artifact page (phone and
   desktop side by side) and ask one yes/no in Russian: "Так выглядит главная газета; оставляем?"
   with your recommendation. If the owner asks for changes, make them and ask once more.
5. Checks once at the end, in this order: `./.venv/bin/pytest` (full suite,
   `PYTHONDONTWRITEBYTECODE=1`), `make lint PYTHON=./.venv/bin/python`,
   `python scripts/check_code_docs.py` if it has a CLI, then crapper, dryer 0.8 and mutator on
   `bulletin_view.py` (see AGENTS.md "Validation"). After a fix rerun only the check that failed.

## Report

Write `specs/018-daily-inference/records/report-item6a-bulletin-design-2026-11-<DD>.md` in the
worktree: what changed (files), decisions you made (one line each, "decided <date> (agent)"), the
owner's answer on the look (quote), checks run with results, anything not run and why, and open
points for 6b. Then tell the owner in Russian, in two lines: done, and that the coordinator session
takes it from here (review, PR, merge).

Keep this rule for any further prompt: save every prompt for another session to a file in
`specs/018-daily-inference/records/` first, never overwrite earlier prompts.
