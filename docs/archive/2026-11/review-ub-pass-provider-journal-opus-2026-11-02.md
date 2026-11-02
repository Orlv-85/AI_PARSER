# Review: ub-mode pass 1, provider journal (2026-11-02)

Reviewer: a fresh Claude Opus agent (Codex limit reached), prompt
`prompt-ub-pass-provider-journal-review-codex-2026-11-02.md`. Verdict: clean.

- Equivalence checked method by method: SQL, reserve -> dispatch -> record -> validate order,
  exceptions, fail() error types, transactions unchanged; `saved` reassignment moved safely.
- Hand mutations on a scratch copy: 14/14 killed (record/validate swap, total and provider cap,
  saved-amount and usage bounds, before_dispatch, reserve after dispatch, error type, provenance,
  exhaustion bound, transport row guard, truncation and restore price match, token filter).
- Doc fixes applied by the coordinator: unknown saved usage blocks without failing the row; three
  tests named in their rules; caps must be exactly total/jev/deepseek; process-history "decided"
  line removed; troubleshooting cause reduced to what is confirmed.
- Tests: 259 passed (journal and callers); `check_code_docs.py --diff origin/master --strict` ok.
