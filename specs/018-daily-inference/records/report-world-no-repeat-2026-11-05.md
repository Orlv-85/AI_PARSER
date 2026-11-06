# World stories do not repeat on consecutive days

Task: `prompt-world-no-repeat-codex-2026-11-05.md` (spec 018).
Branch: `fix/018-world-no-repeat`.

## Files changed

- `src/app/core/bulletin/builder.md`: behavior, named regression tests, the prescribed
  2026-11-05 decision, and helper code map.
- `tests/unit/test_bulletin_builder.py`: seven new test functions (39 parameterized cases),
  stored-payload fixtures, and optional title/GDELT stamp in the existing world fixture.
- `src/app/storage/bulletin_input.py`: collect the previous ready bulletin's URLs and title
  keys, then filter world candidates before reading their assessments.
- This report.

## Rule implemented

Only `BulletinRepo(session).get(D - 1)` is read. A ready row supplies every story in
`key_results`, `rubric_story`, `cooperation`, and `incident_story`, regardless of origin.
A world candidate is excluded if its exact URL occurs in any story link or its title's
`cluster_key` equals a stored story title's `cluster_key`. Matching does not use the
candidate's persisted cluster-key column, URL canonicalization, or writer headlines.

A missing row, a non-ready row, or a malformed payload supplies no exclusion keys. Payload
extraction is atomic: a malformed story discards both sets rather than keeping partial
URL matches. Digest candidates and their order are unchanged. The existing world switch
and production settings are unchanged.

Decision supplied by the task: the world window spans D-1 and D, so only D-1 is checked.
Implementation detail decided by the agent: malformed payload structure fails open as a
whole, using the documented stored shape and catching attribute/key/type errors.

## Test first evidence

The behavior doc was edited first, then tests were added and run before implementation.
An initial fixture incorrectly called the builder with no assessments; it was corrected
to use an assessed `none` candidate for an empty ready payload before recording the red run.

Corrected pre-implementation run: **24 failed, 15 passed, 88 deselected**, one existing
Starlette deprecation warning. All 24 failures were the expected extra world candidate.

| New test | Cases | Before implementation |
| --- | ---: | --- |
| `test_world_candidate_shown_yesterday_is_left_out` | 8 | Failed: yesterday's exact URL remained. All four sections and both origins; matching link is second, with a different story title. Candidate comes from GDELT D-1. |
| `test_world_candidate_syndicated_copy_shown_yesterday_is_left_out` | 16 | Failed: different URL, same normalized title key remained. All sections and origins; punctuation/case normalization and truncated title keys. |
| `test_world_candidate_kept_when_yesterday_skipped_or_missing` | 2 | Passed: retention controls already match baseline behavior. The skipped row contains a matching story. |
| `test_world_candidate_kept_when_yesterday_payload_is_unreadable` | 6 | Passed: baseline never reads the payload. Tests null, non-object, missing sections, wrong section type, malformed link, and missing title with a matching URL. |
| `test_world_candidates_not_compared_beyond_yesterday` | 3 | Passed: retention controls with matching D-2 and missing, skipped, or empty ready D-1. |
| `test_digest_candidates_ignore_yesterday` | 2 | Passed: matching URL and title remain in digest input, with the world switch both off and on. |
| `test_world_candidate_not_shown_yesterday_is_kept` | 2 | Passed: unrelated and similar-but-unequal title keys remain eligible. |

The retention controls cannot honestly fail on the baseline: the bug is excess inclusion,
not excess exclusion. They guard against implementing the fix too broadly.

After implementation: **127 passed**, one existing warning, in the feature test file.
Ruff on the two changed Python files passed (two initial overlong test decorators were wrapped).

## Final checks

Checks were started in the requested order: full suite, make lint, crapper, dryer, mutator.
All commands used the supplied offline environment and main checkout's virtualenv where
specified. No full-suite or lint gate was run during implementation.

1. Full suite: the exact requested `pytest -q` command exited 0. Its combined CLI/config
   quiet flags suppress the numeric summary; there were 2,350 collected node IDs and two
   skips. Crapper's subsequent coverage run confirmed **2,348 passed, 2 skipped, 1 warning**
   (160.95 seconds under coverage). Both skips require the unset `AINEWS_TEST_POSTGRES_URL`;
   the warning is the existing Starlette/httpx deprecation.
2. `make lint`: repository-wide Ruff passed; mypy reported no issues in **274 source files**.
   Pylint initially reported one `too-many-positional-arguments` error on the expanded
   world test fixture. The two new options were made keyword-only, preserving its existing
   positional API. Only the failed component was rerun (`make lint-pylint`), successfully:
   **10.00/10**. Ruff/mypy were not needlessly repeated.
3. Crapper: exit 0; all functions in the file reported **100% coverage**. Changed functions:

   | Function | CC | CRAP |
   | --- | ---: | ---: |
   | `_bulletin_story_keys` | 2 | 2.0 |
   | `_yesterday_story_keys` | 4 | 4.0 |
   | `_world_candidates` | 5 | 5.0 |

   **Maximum changed-function CRAP: 5.0** (under 10). Maximum for the entire file: 7.0
   (`load_day_input`, unchanged). Output: `.metrics/crap.edn`; coverage:
   `target/coverage/python/lcov.info`.
4. Dryer, threshold 0.8: exit 0, **No duplicate candidates found.** Output: `.metrics/dry.edn`.
5. Mutator, exact requested existing-coverage command and feature-only test command: exit 0.
   Output: `.metrics/mutate/app.storage.bulletin_input.edn`.

   ```text
   Function              Killed  Survived  Uncovered  Sites   Score
   _bulletin_story_keys       0         0          0      0     n/a
   _yesterday_story_keys      4         0          0      4  100.0%
   _world_candidates          1         0          0      1  100.0%
   Total (entire file)       27         0          3     30  100.0%
   ```

   All five mutation sites in changed code were killed: D-1 subtraction, day offset,
   missing/non-ready guard boolean, ready-status comparison, and URL/title match boolean.
   `_bulletin_story_keys` has no supported mutation sites; its behavior is exercised by
   all section/origin cases and malformed-payload controls. There are **no survivors**
   requiring a justification or additional regression test.

   Three sites were marked uncovered and were not run by the coverage-filtered command:
   line 62 (`<` -> `<=`), line 63 (`>=` -> `>`), and line 63 (`-` -> `+`), all in the
   unchanged `_median_items` SQL query. This matches the existing troubleshooting case
   `mutator-lcov-multiline-sites-uncovered`: Crapper reports the function covered, but
   LCOV does not mark these multiline token positions. No new-code site was uncovered.
   No additional mutation pass was run: the required pass succeeded, no survivors
   remain, and these sites are outside this change.

`git diff --check` also passed. All five requested checks ran; no required command was
omitted. PostgreSQL integration behavior was not exercised because the test URL is unset.

## Scope and handoff

No commit, push, gh command, external network request, paid call, sub-agent, or separate
doc review was initiated. The requested separate reviewer should review code and doc.
Prompts for other sessions must be saved under the feature's `records/` before delivery;
no handoff prompt was requested or created here.
