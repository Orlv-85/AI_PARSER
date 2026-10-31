<!-- code-doc
module: src/app/core/world/__init__.py
covers:
  - src/app/core/world/*.py
-->
# World news stream

Candidate stories about AI in human life from outside our own sources, for the Daily Inference
bulletin (spec `specs/018-daily-inference/spec.md`, FR-014..FR-018). Plan:
`specs/018-daily-inference/records/plan-item5-world-sources-2026-10-31.md`. Shipped so far: the
keyword filter (W1). The GDELT reader (W2) and everything after it are not in the code yet.

## Behavior

```mermaid
flowchart LR
  row["GDELT row: title, url, themes"] --> kw{"AI keyword in the title?"}
  kw -- no --> out["Dropped: no_match"]
  kw -- strong --> drops
  kw -- weak --> weak{"IA, KI, robot or algorithm?"}
  weak -- no --> out2["Dropped: weak_not_ai"]
  weak -- yes --> drops
  drops{"own domain, finance domain, finance theme, finance title?"} -- any --> out3["Dropped with its reason"]
  drops -- none --> kept["Kept: candidate"]
```

- The filter reads only the title, the URL and the GDELT themes of a row. It uses no network and
  no database. Tests: `test_filter_has_no_io_imports`.
- A title matches strongly on a phrase list in many languages (`STRONG_PHRASES`) or on the
  capitalised tokens `AI`, `ИИ`, `ШІ`, `GPT` (`STRONG_TOKENS`); phrases ignore case, tokens do not.
  `AI` is a token when no letter or digit stands before it and no letter after it: "AI-generated"
  and "AI技术" match; AIDS, AIIB, AIFF, AIRPORT do not. Tests: `test_filter_ai_token_is_a_word`.
  A headline written entirely in capitals (at least `ALL_CAPS_MIN_LETTERS` cased letters) does not
  match on `AI`; a CJK title with a Latin `AI` is not a capitals headline. Tests:
  `test_filter_strong_phrases_in_many_languages`, `test_filter_all_caps_title_is_not_strong`,
  `test_filter_cjk_title_with_ai_is_strong`.
- A weak match (`WEAK_WORDS`, `WEAK_TOKENS`) is kept only with "robot", "algorithm" or `IA` / `KI`
  (capitals) in a context (`WEAK_KEEP_RE`): after an article or preposition ("la IA", "de KI"),
  with a hyphen ("KI-Suche"), before "generativ...", or as the first word. "Des Moines, IA" and
  "Mi KI es tu casa" are dropped. Other weak matches are dropped. Tests:
  `test_filter_weak_requires_ia_ki_or_robot`, `test_filter_ia_ki_need_context`.
- Names and stems that gave false hits do not match: Alexa, Siri, Gemini, Claude, "automat...",
  and "Ai" inside a name or a longer word. Tests: `test_filter_ignores_names_alexa_ai_and_automatically`.
- A title is dropped when it has a finance word (`FINANCE_TITLE_RE`), when a GDELT theme is in
  `FINANCE_THEMES`, or when the host is in `FINANCE_DOMAINS` or a subdomain of one. Words that
  also mean something else (shares, stock photos, actions, акции, 基金, инвест) are not finance
  words alone, so human-life stories stay. Tests: `test_filter_drops_finance_titles_and_themes`,
  `test_filter_drops_finance_domains`, `test_filter_keeps_slguardian_org`,
  `test_filter_keeps_human_life_stories_with_money_words`.
- A title is dropped when the host is one of our own source domains or a subdomain of one:
  `feeds.arstechnica.com` as a source makes `arstechnica.com` and `www.arstechnica.com` own.
  `load_own_domains` reads the hosts of all sources in `sources.yaml` and cuts the prefixes in
  `FEED_HOST_PREFIXES`. Hosts on `SHARED_PLATFORM_DOMAINS` (medium.com, github.com,
  microsoft.com, feedburner.com and similar) are not own: their stories are not ours. Tests:
  `test_filter_own_domains_skip_shared_platforms`, `test_filter_drops_own_registrable_domains`,
  `test_load_own_domains_cuts_feed_prefixes`, `test_load_own_domains_reads_repo_sources`.
- On 60 real titles of a measured day (30 kept, 30 dropped) the result equals the recorded one.
  The expected values were recorded from this filter and read by hand; the fixture pins the
  behavior and is not an independent judgement. Tests: `test_filter_real_title_fixture`.

## Decisions

- Keyword filter on the title, not a GDELT theme filter: GDELT has no AI theme (measured on one
  day, 2026-10-31).
- Weak words need a second signal because `IA`, `KI` and "robot" collide with other words; names
  and "automat..." were removed after false hits on a hand-checked sample.
- Own-domain match is by suffix, not by exact host, so feed and `www` subdomains do not leak our
  own sources into the stream. Only the prefixes in `FEED_HOST_PREFIXES` are cut; a source on a
  shared host (a project page on a hosting provider) is not own at all
  (`SHARED_PLATFORM_DOMAINS`, decided 2026-10-31 by the coordinator).
- `slguardian.org` is a general news site; it was listed as finance by mistake and is removed.
- Dedup (same canonical URL, same first 60 normalized title characters) is not part of the filter;
  it belongs to storage (W3).
- The footer credit "News discovery: GDELT Project" with a link is required by the GDELT terms
  and approved by the owner (2026-10-31); the digest Jev cap of FR-012 stays $0.05 per day,
  and the world stream has its own Jev cap of $0.10 per day (owner, 2026-10-31), inside the
  approved $3 per month. Both are used by later steps; neither is in the code yet.

## Invariants

- The filter module imports no network, database or web code and never touches `articles`
  (FR-016). Tests: `test_filter_has_no_io_imports`.
- Production has 3.6 GB of free disk and 2 GB of RAM: the reader (W2) keeps no raw GDELT file and
  holds no whole-day list of raw rows. This is binding for W2 and later steps.

## Code map

- `filter.py`: keyword lists, `classify_title`, `filter_title` (result `FilterResult` with a
  reason), `load_own_domains`, `own_domains_from_hosts`, `host_in_domains`.
- Change a keyword or a drop rule in the constant named above and extend the fixture test.

## Tests

- `tests/unit/test_world_filter.py`: all rules above.
- `tests/fixtures/world/titles.jsonl`: 60 real titles from the measured day, each with the
  recorded decision.
