# Prompt: user agent options, a decision note for the owner (2026-10-28)

Executor: background agent (Sonnet) of coordinator `ai-parser-ba`. Research and write a short note;
change no code. Production is read-only (log grep only).

## Question

The fetcher and the archive send `DEFAULT_USER_AGENT`, which imitates a browser. Should the app send
an honest bot user agent instead (e.g. `ai-news-collector/<version> (+https://<site>/about-bot)`)?
The owner decides; the note must make the choice easy.

## Collect

1. Where `DEFAULT_USER_AGENT` and any other user agents are defined and used (file:line): RSS fetch,
   HTML fetch, full-text extraction, archive capture, source onboarding probes.
2. Facts from prod logs (`ssh -o BatchMode=yes ai-news`, only `grep`/`tail` on
   `/opt/ai-news/logs/daily-fetch.log` and `daily-archive.log`): which hosts answer 403/429 today
   (e.g. openai.com for the archive), per host counts over the last 7 nights.
3. Whether the app reads robots.txt (and for which requests), and what it does with it.
4. Options, each with what changes for the sources we collect: (a) keep the browser UA; (b) honest
   bot UA for everything; (c) honest bot UA plus a per-source override in `sources.yaml` for hosts
   that block bots; (d) honest UA for the archive only. For each: expected effect on blocked hosts
   (say what is known vs guessed), effort (files, tests), and legal/policy notes (site terms usually
   forbid impersonation; many publishers allow declared crawlers; no legal advice, just the facts).
5. A recommendation in two lines.

## Output

Write the note to `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/report-ua-options-2026-10-28.md`
(English, under ~80 lines: question, facts, options table, recommendation, the yes/no question for
the owner). No commit, no PR. Final answer: the recommendation and the yes/no question.
