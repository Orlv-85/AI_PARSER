# Daily Signals Brief fixtures (007)

Copied on 2026-10-19 from the Phase A dry-run (`tmp/007-brief-dryrun/` of the planning worktree,
see `specs/007-daily-signals-brief/dry-run.md`). JSON re-encoded as ASCII (`\uXXXX`
escapes); the content is unchanged.

- `sig-2026-10-12.json` .. `sig-2026-10-18.json`: production `GET /api/news/daily-signals?date=`
  answers (methodology `daily-signals-2`), renamed from `sig-DD.json`.
- `dig-2026-10-12.json` .. `dig-2026-10-18.json`: production `GET /api/news/digests?date=` answers,
  renamed from `dig-DD.json`.
- `responses.json`: every raw DeepSeek answer of the dry-run, keyed by the sha256 of the sorted
  request body: 37 calls of dry-run sections 1-2 (prompt `daily-signals-brief-1`, incl. the discarded
  run 0) and 6 calls of section 5 (`daily-signals-brief-2`, runs A and B). Models `deepseek-v4-pro`
  and `deepseek-flash`.
- `answers.json`: per `<day>/<model>` (revision 1, 14 pairs): the packet sent, the attempts (model,
  finish reason, tokens, result code; rejected attempts keep their `raw` content) and the accepted
  sentences.
- `report-rev2.json`: revision 2 run B (`daily-signals-brief-2`, pro, 10-13/15/16): packet (`data`)
  and the brief (attempts, sentences).
- `one_liners.json`: the 40 New items of the 7 days, keyed `<day>/<name>`, with the expected one-liner
  and its source (`summary` | `quote`) under the plan P3 rule.

Packets were built from the API answers (at most 3 links per item); the code builds them from the
stored snapshot. Provider answers are real; none is hand-written.
