# Prompt: reference labels for the world_change questions (spec 018, item 1, 2026-10-31)

You label news articles by hand, as an independent reference for an automatic classifier (Jev).
You never see the classifier's answers. **No code changes, no commits, no network, no paid calls.**
Write one output file and report in English.

## Read first

The spec is on `origin/master`, not in the main folder's working tree; read it without touching
the tree, from `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`:

- `git show origin/master:specs/018-daily-inference/spec.md`: sections "The idea", "Editorial
  rules", FR-001, FR-003.
- `git show origin/master:specs/018-daily-inference/voice.md`: section "Areas".

## Input

`/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/8230bf51-ec40-4f65-b975-34c791a2cee9/scratchpad/world-change-sample.jsonl`:
260 lines, one JSON object each: `day`, `url`, `event_type`, `title`, `summary`, `content`,
`url_canonical_hash`. Read title and the first ~2000 characters of `content` (more when unsure).
Process it in chunks with a small Python script that prints articles (use `python3 -I`); do not
paste the whole file at once.

## Questions (answer all four per article)

1. `world_change`: what does this article say about how AI changes the real world?
   - `added`: a new AI capability or product that people or organisations can now use.
   - `changed`: AI took over or changed real work, money, law, science, health, education, culture
     or daily life (adoption, effects, deals, deployments, measured outcomes).
   - `issue`: a failure, attack, misuse, risk or harm involving AI.
   - `limit`: people set rules or limits for AI: laws, court rulings, regulators, company policies
     and guidelines, opt-outs, bans.
   - `none`: the inside kitchen of the AI industry with no effect stated: opinion, tutorials,
     benchmarks only, how-to guides, minor updates, newsletters.
2. `area`: one of Work, Money, Law, Science, Health, Education, Speech, Daily life, Culture, Faith,
   Security, Infrastructure, Governance.
3. `actor`: who acts in the main event: `ai_system` (an AI model or agent did it itself),
   `people` (people did it, possibly with AI tools), `organisation` (a company, institution or
   government did it).
4. `harm_to_people`: `yes` if real people were hurt or are at concrete risk (death, abuse,
   self-harm, fraud victims, a named private person in trouble, job loss of named people); else `no`.

Also give `confidence` per article: `high`, `medium` or `low`.

## Output

Write `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/8230bf51-ec40-4f65-b975-34c791a2cee9/scratchpad/world-change-labels.jsonl`:
one line per input article, same order:
`{"url": ..., "world_change": ..., "area": ..., "actor": ..., "harm_to_people": "yes"|"no", "confidence": ..., "note": "<=12 words, why"}`.
All 260 lines; check the count before you finish.

## Report (your final message, short)

Counts per `world_change` value and per day; the 5 hardest cases with one line why; anything in the
question wording that was ambiguous.
