# Prompt: send the feed description to admission when an item has no text (2026-10-23)

Run only after the owner answered "yes" to question 1 of `docs/report-openai-source-2026-10-23.md`.

You are the implementer for `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. Read `AGENTS.md` first and
follow it. Work only in the worktree below; do not write to git in the main folder. Do not merge,
tag or touch prod. Save any prompt for another session as a file (AGENTS.md "Prompts For Other
Sessions").

## Facts (prod, read-only, 2026-10-23; details in the report)

- Prod runs with `AINEWS_DAILY_ENRICHMENT_ENABLED=true` and `AINEWS_SEMANTIC_ADMISSION_ENABLED=true`.
- In that mode `JevRelevanceScorer.state` (`src/app/core/jev.py`) returns
  `jev_state(article, with_summary=False)` = `Title: ...\nContent: ...`. The RSS description
  (`Article.summary`) is not sent.
- openai.com article pages answer 403 (Cloudflare challenge), so OpenAI candidates have no content
  and Jev decides on the title alone: 23 of 29 recent candidates `insufficient_evidence`.
  TLDR (`bullrich-dev-tldr-rss-ai-rss`) loses 33 of 170 the same way.
- `state()` is called only on the ingestion path (`classify`, `score`, and the in-cycle cache check
  in `pipeline._screen_candidate`). Re-enrichment and daily enrichment build their own text
  (`reenrich_pilot.source_state`), whose reason to drop the summary ("may be generated") does not
  hold at ingestion: there the summary is the publisher's feed description.

## Decided by the coordinator (2026-10-23, agent)

- Daily mode, candidate content empty or whitespace: `state()` returns the full bounded text
  `jev_state(article)` (`Title / Summary / Content`, the same text plain admission already sends).
  Candidates with content keep `Title / Content`. Plain (non-daily) mode is unchanged.
- The admission cache key is unchanged: `bounded_evidence` already hashes title + summary +
  content. Already cached decisions stay; the 2015+ OpenAI archive is not re-screened. No prompt
  or policy version bump, no env change.
- The enrichment provenance hash (`_build_article_row`, `jev_state(item, with_summary=False)` in
  `pipeline.py`) stays title + content, so `daily.admission_from_proof` keeps reusing the answer.
- The daily digest is not changed (feed-only items stay held for lack of source text).
- Weekly copies of the daily text (`core/weekly/input.py`, `core/weekly/frozen.py`) are not changed.

## Setup

```
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch origin
git worktree add ../AI_PARSER-wt-feed-description -b fix/feed-description-admission-20261023 origin/master
cd ../AI_PARSER-wt-feed-description
```

Checks in the worktree: `PYTHONPATH=src ../AI_PARSER/venv1/bin/python ...`,
`PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest ...`.

## Steps (doc first)

1. `src/app/core/ingestion/pipeline.md`, "Semantic admission": add a rule after the one that starts
   "Each eligible candidate not yet stored gets one Jev assessment": "With daily enrichment the
   assessment text is title and content; a candidate without content (an RSS item whose page could
   not be extracted) is assessed on title, feed description and content. The cache key and the
   enrichment provenance hash do not change." with `Tests:` naming the three tests of step 3.
   Add one Decisions row: "Feed description is admission evidence only when there is no content |
   decided 2026-10-23 (agent): without it Jev decides on the title alone (openai.com answers 403;
   23 of 29 OpenAI candidates unresolved); the summary is dropped elsewhere because a stored summary
   may be generated, but at ingestion it is the publisher's feed text. Cached decisions are kept so
   the feed archive is not re-screened". In the Code map row "Evidence bound sent to Jev" add
   that `JevRelevanceScorer.state` adds the summary for content-less candidates in daily mode.
2. Code, `src/app/core/jev.py`:
   - `JevRelevanceScorer.state`: if `self.daily_enrichment_enabled` and
     `not str(getattr(article, "content", "") or "").strip()`, return `jev_state(article)`;
     otherwise the current line. One short comment: "No page text: the feed description is the
     only evidence besides the title."
   - `jev_state` docstring: replace "(the daily rubric leaves out the summary)" with "(the daily
     rubric leaves out the summary unless there is no content)".
   Change nothing in `pipeline.py`, `admission.py`, `reenrich_pilot.py`, `enrichment.py`, weekly.
3. Tests:
   - `tests/unit/test_jev.py`: add mode `"daily_feed_only"` to
     `test_bounded_jev_text_is_pinned_per_mode`: article `_pinned_article(content=None)` (summary
     kept), `sent = _sent_state(article, admission=True, daily=True)`; assert
     `sent == bounded_evidence(article)`; build the row as in the `daily_enrichment` branch and
     assert `provenance["admission_source_hash"] == fingerprint(source_state({"title":
     article.title, "content": ""}))`; pin `PINNED_TEXT["daily_feed_only"]` (compute it once).
     The existing four pinned values must not change.
   - `tests/unit/test_jev.py`: `test_daily_feed_only_candidate_sends_feed_description`: daily mode,
     content `None` and summary `"Feed line"` -> sent state contains `"Summary: Feed line"`;
     content `"   "` -> same; content `"Body"` -> state has no `"Summary:"`.
   - `tests/unit/test_daily_enrichment.py`: `test_feed_only_admission_is_reused_by_enrichment`,
     modeled on `test_ordinary_ingestion_uses_rubric_journal_and_reusable_admission`: item with
     `content=None` and a summary; one Jev call whose `state` contains the summary;
     `daily.admission_from_proof(row, {"title": item.title, "content": ""})` returns the answers.
4. Checks: `./venv1/bin/python -m ruff check src tests` (via the worktree paths above),
   `pytest tests/unit/test_jev.py tests/unit/test_daily_enrichment.py
   tests/unit/test_semantic_admission.py tests/unit/test_semantic_admission_pipeline.py`, then the
   full gate: `make lint PYTHON=../AI_PARSER/venv1/bin/python` and the full `pytest`
   (`scripts/check_code_docs.py` runs inside it).
5. Commit (one commit):

```
fix(admission): send the feed description to Jev when an item has no page text

With daily enrichment the admission text was title + content only. An RSS
item whose page cannot be extracted (openai.com answers 403) was judged on
its title alone: 23 of 29 recent OpenAI candidates ended
insufficient_evidence. Such candidates now send title, feed description and
content, the text plain admission already sends. Cache keys, enrichment
provenance, digest and weekly texts are unchanged; cached decisions stay.

Co-Authored-By: <your attribution line>
```

6. Push and open the PR:

```
git push -u origin fix/feed-description-admission-20261023
gh pr create --base master --head fix/feed-description-admission-20261023 \
  --title "fix(admission): send the feed description to Jev when an item has no page text" \
  --body "$(cat <<'EOF'
## Why
openai.com article pages answer 403, so OpenAI candidates have no text and, with daily
enrichment, Jev saw only the title: 23 of 29 recent candidates were insufficient_evidence
(docs/report-openai-source-2026-10-23.md).

## What
- `JevRelevanceScorer.state`: daily mode, no content -> title + feed description + content.
- pipeline.md: admission rule, decision row, code map.
- Cache keys, enrichment provenance hash, digest, weekly: unchanged. No new paid calls; no
  re-screen of cached candidates.

## Tests
- test_bounded_jev_text_is_pinned_per_mode[daily_feed_only]
- test_daily_feed_only_candidate_sends_feed_description
- test_feed_only_admission_is_reused_by_enrichment
- Gate: make lint, full pytest: <results>

## After deploy
Compare openai_news and bullrich-dev-tldr-rss-ai-rss unresolved shares of new candidates
(report SQL) after 3 daily runs.
EOF
)"
```

## Report (reply to the coordinator, saved as `docs/report-feed-description-admission-2026-10-23.md` in the same PR)

- PR link, commit hash.
- Files changed with one line each.
- Gate results: ruff, make lint, full pytest counts (passed / failed / skipped); anything not run
  and why.
- The three new tests and the new pinned hash; confirm the four old pinned hashes are unchanged.
- Any place where the facts above did not match the code, and what you did.
- Open questions, one line each (AGENTS.md "Owner And Questions").
