1. **Same behavior: nothing found.** Compared both old openers and both exception handlers against HEAD, including an AST-normalized comparison. Caps, paths, filenames, identities, review reasons, retries, secrets, timeouts, headers, key-check order, logging order and exception order are unchanged. Differences are the stated relocations and replacement of dynamic lookups with imports.

2. **Stop-error identity: nothing found.** Searched definitions, raises and catches throughout `src/` and `tests/`. Each exception has one definition. Runtime identity assertions confirmed that storage’s compatibility exports and the core handlers reference the same class objects.

3. **Import cycles: nothing found.** All eight requested entry points imported successfully, each in a fresh interpreter with `PYTHONPATH=src` and bytecode writing disabled.

4. **Ineffective monkeypatches: nothing found.** `cli_main.open_assessor` and `cycle.jev_relevance_scorer` remain the names read by their callers. The remaining `wc.httpx.Client` patches work because the opener and `wc` share the same `httpx` module object. No relevant `setattr(..., raising=False)` conceals a removed target.

5. **Should fix — exceptional cleanup is not pinned**, [test_jev.py:348](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/019-t014/tests/unit/test_jev.py:348) and [test_world_change.py:621](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/019-t014/tests/unit/test_world_change.py:621). The new tests exit their contexts normally. Moving reporting and closing out of `finally` to immediately after `yield` would survive these tests while leaking the journal when the context body raises. This survivor is inferred from inspection, not an executed mutation.

   The daily test checks caps, path, identity, retry configuration, authorization, normal close and usage logging; the disabled-daily test checks absence of a journal and data directory. The new assessor test checks usage logging, while the existing `test_open_assessor_caps_the_journal` checks caps, path, identity, retries and normal close. Neither new opener test pins timeout or exceptional cleanup.

   **Note — pre-existing cleanup weakness**, [assessor.py:51](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/019-t014/src/app/usecases/bulletin/assessor.py:51) and [scorer.py:55](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/019-t014/src/app/usecases/ingestion/pipeline/scorer.py:55): if `journal.report()` or logging raises, `journal.close()` is skipped. Both original bodies have the same weakness; this is not a new regression.

6. **Note — the layer test does not cover every import form**, [test_layer_imports.py:18](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/019-t014/tests/unit/test_layer_imports.py:18). Executing its scanner against `from importlib import import_module as load; load("app.storage.provider_journal")` returns `False`; so does assigning the module name to a variable before calling `import_module`. Thus passing proves only the supported syntactic forms. Inspection found no such hidden storage import currently in `core/`.

7. **Should fix — journal ownership documentation is stale**, [provider_journal.md:130](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/019-t014/src/app/storage/provider_journal.md:130). It still says `core/jev.py` and `core/bulletin/world_change.py` choose journal identity, caps and retries. Those choices now belong to the two use-case openers, as confirmed by their constructors.

   **Note — stale count**, [tasks.md:74](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/019-t014/specs/019-layer-boundaries/tasks.md:74): T015 still counts two core files importing `app.config`; only `core/sources/review.py` remains. Nothing else found in the requested documentation.

8. **Stale qualified opener references: nothing found.** Searched tracked files and hidden configuration outside the specified history directories, and inspected all remaining opener-name references.

Validation: **304 requested feature tests passed**, with one Starlette deprecation warning. Not checked: full suite, lint, live providers, production databases, remote CI status or executed mutations. No files changed.
---

## Outcome (coordinator, 2026-11-11)

Reviewer: Codex `gpt-6-astra`, effort high, fresh read-only session on a detached worktree of
commit 9842cc2; prompt `prompt-t014-review-2026-11-11.md`. Each finding was checked in the code.

- 1-4, 8 (nothing found): accepted.
- 5 should fix (cleanup on failure not pinned): confirmed and fixed. New tests
  `test_daily_scorer_closes_journal_when_the_run_fails`,
  `test_open_assessor_closes_journal_when_the_run_fails`. The mutation the reviewer named (report
  and close only on success: `try/except/else` instead of `finally`) was applied to each opener by
  hand: each new test fails on it (journal not closed), restored after.
- 5 note (`journal.report()` raising skips `close()`): confirmed, same in the old code; not changed,
  the PR keeps behavior.
- 6 note (layer scan misses `import_module` under an alias or with a variable name): confirmed as a
  limit of the scan; no such form exists in `core/` now. Not changed in T014.
- 7 should fix (`provider_journal.md` still named the core files as journal owners): confirmed and
  fixed; the code map now lists the four use-case openers.
- 7 note (T015 counted two core files importing `app.config`): confirmed and fixed in `tasks.md`.
