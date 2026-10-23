# Prompt: why OpenAI news barely reach the site, and what to do (2026-10-23)

You investigate and propose; you do not change code. Repo: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`.
Read `AGENTS.md` first and follow it. The owner writes Russian and takes part minimally: decide
technical questions yourself; only a change of what readers see, or of paid calls, goes to the
owner as a one-line yes/no question with a recommendation.

## Known (coordinator, prod read-only, 2026-10-22)

- Source `openai_news`, feed `https://openai.com/news/rss.xml`: the feed holds the whole archive
  since 2015 (~1360 items); each item has a title and a one-line description only.
- Article pages answer HTTP 403 to the server (bot protection); full-text extraction logs
  `rss.full_text_extract outcome=failed ... error=RuntimeError` for every item.
- With title + one line, Jev admission mostly answers `insufficient_evidence`: last 30 days 1
  accepted, 4 rejected, 21 unresolved. Fresh OpenAI announcements therefore miss the site and the
  daily digest. (Replaying old pending candidates is handled by a separate fix.)
- Admission rules: `src/app/core/ingestion/pipeline.md` ("Admission" rules), `src/app/core/jev.py`
  (`questions()`, admission choices). Digest needs source text for grounded summaries:
  `src/app/core/daily/enrichment.md`.

## Tasks

1. Measure (prod read-only via `ssh ai-news`, see `docs/deploy.md`; no writes, no restarts, no
   paid calls): for every enabled source, share of new candidates of the last 30 days that ended
   `unresolved`, and of articles without full text. List the sources that behave like OpenAI
   (403 or empty text). Give the SQL/commands you used.
2. Check how other sources already cover OpenAI announcements (are the same stories admitted via
   TechCrunch, The Verge, etc. within a day?). Use the stored articles; say how many of the 21
   unresolved OpenAI items of the last 30 days reached the site through another source.
3. Compare options, each with what readers would see, cost, risk and size of the change:
   a) admit trusted first-party sources (vendor blogs) on title + description, with a flag
      (`evidence: feed_only`), and how the digest should show them (title + link without a
      generated summary?);
   b) another feed or API from the same vendor that carries text (only legitimate, documented
      endpoints; do not propose bypassing bot protection);
   c) rely on secondary coverage (no change);
   d) anything better you find.
4. Write the report `docs/report-openai-source-2026-10-23.md`: numbers, options table, your
   recommendation, the owner question(s) in Russian as yes/no with a recommendation, and if the
   recommendation needs code, an exact implementer prompt saved as
   `docs/prompt-<task>-2026-10-23.md` (step by step: worktree, branch, doc first, code, tests,
   checks, commit message, full `gh pr create`, report fields).
5. Open one docs PR with the report (and the prompt, if any) from a worktree off `origin/master`,
   branch `docs/openai-source-report-20261023`; docs only, gate not run (say so). Do not merge.
   Reply with the PR link and the owner question(s).
