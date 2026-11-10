# Review of PR 221 (spec 019 step 2), 2026-11-10

Reviewer: a fresh agent session, read-only, prompt `prompt-step2-review-2026-11-10.md`.
Coordinator check: every "should fix" was verified in the code before the change.

| # | Severity | Finding | Outcome |
| --- | --- | --- | --- |
| 1 | should fix | `core/jev.py` and `core/bulletin/world_change.py` load `app.storage.provider_journal` with `import_module`; the layer test did not see it and the README said "no exceptions" | Confirmed. The scan now reads `import_module`/`__import__` with a literal name; the two files are a listed exception; README corrected; removal is T014 |
| 2 | should fix | `docs/troubleshooting.md` cited `_html_placeholder_key` in a file that does not exist | Fixed (the path was already stale before the PR) |
| 3 | should fix | `core/periodic/signals_period.md` named the two moved modules as siblings | Fixed: full paths |
| 4 | should fix | `usecases/daily/enrichment.md` code map: bare `provider_requests.py`, no entry for `titles.py` | Fixed |
| 5 | note | `docs/backlog/*.json` kept old paths, three of them in prompts for future sessions | Fixed: paths only |
| 6 | note | `spec.md` named the removed list and test | Fixed |
| 7 | note | bare "see `daily.md`" / "see `capture.md`" / `writer_run.py` in docs that stayed in `core/` | Fixed: full paths |
| 8 | note | the scan misses relative imports | A test bans relative imports in `src/app` (there are none) |
| 9 | note | `core/` imports `app.ingest` and `app.config`; `ingest/` imports `core/` back; `config/sources.py` loads storage models by name | Not in this PR: T015 |
| 10 | note | `tests/unit/test_world_storage.py`: banned prefix `app.storage.world.` has a trailing dot, so `import app.storage.world` in a web module passes; both web guards check direct imports only | Not in this PR: on master before it, not caused by the move; reported to the owner |
| 11 | note | `scripts/check_code_docs.py` docstring example matches the real header only in part | Left: an example |

Pure move (point 1 of the prompt), runtime dependence on module paths (point 6): nothing found.
Not checked by the reviewer: full pytest, `make lint`, UB tools, Docker image build, production.
