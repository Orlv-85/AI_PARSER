# Semantic admission spec (2026-10-10)

## Gate
`semantic_admission_enabled=False` preserves legacy behavior. When true, after deterministic non-news filtering and before article row creation, each candidate is assessed with one JEV admission/choice question. The same JEV request keeps existing relevance/category questions.

## Choices and mapping
- `accepted_ai_editorial` -> accept, reason `AI_EDITORIAL`
- `non_ai` -> reject, reason `NON_AI`
- `non_editorial` -> reject, reason `NON_EDITORIAL`
- `insufficient_evidence` -> unresolved, reason `INSUFFICIENT_EVIDENCE`

Missing date alone is not a rejection reason. Category parse failure does not invalidate a valid admission answer. Invalid admission, provider missing/disabled, timeout, 429 or 5xx is screening unavailable, not an article decision.

## Outage behavior
When screening is unavailable, collection pauses for the cycle. Already verified accepted articles are saved. Unchecked candidates are stored in a durable admission ledger for later replay. No keyword fallback runs in enabled mode. No DeepSeek per-article fallback runs. The exact durable notice is:

`News collection is paused because AI screening is unavailable. Admin: please check the AI providers and configuration.`

The notice is stored in `collection_status` and survives process restarts, empty/304/cache-only cycles and attempted retries. It clears only after a fresh successful semantic assessment.

## Ledger and cache
`admission_decisions` stores canonical URL hash, bounded sent evidence hash, model/prompt/policy key, candidate payload needed to replay unscreened items, assessment/decision/reason and provider status. Rejected and insufficient_evidence decisions are cached and are not repeatedly sent to the paid model while evidence and policy version are unchanged. Pending provider outages are retried on a later ordinary `run_fetch_cycle`.

## Counters and compatibility
FetchSummary adds backward-compatible `semantic_rejected`, `semantic_unresolved`, `semantic_cache_hits` and `screening_paused`. Weekly raw observations are still recorded before the admission gate. Weekly report/coverage semantics and parser_failure are not changed because of semantic rejection.

## Prompt versioning and cache
`admission_cache_key` includes canonical URL hash, bounded evidence hash, model,
policy version and prompt version. Changing the JEV admission prompt without
bumping either version intentionally leaves old cached decisions valid.

## Offline check plan
Run unit tests with isolated SQLite and mocked httpx transports. Real provider
calls are forbidden. Cover disabled compatibility, accept/reject/ambiguity,
undated items, malformed admission with valid category, provider outage after an
accepted batch, durable notice clear, cache reuse, corrupt cached accept
re-evaluation, and pending replay through 304/feed rotation. Weekly coverage is
not marked parser_failure merely because semantic admission rejected an item.
