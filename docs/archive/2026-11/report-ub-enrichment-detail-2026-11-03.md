# Daily enrichment ub-mode pass

Worktree: `refactor/ub-enrichment`. No commits, pushes, gh commands, network access,
paid requests or sub-agents. Provider tests use synthetic HTTP responses and isolated SQLite.

## Changes

- `src/app/core/daily/enrichment.py`: extract applied-summary limits, source hash, stored fallback,
  review flags, summary request construction, length validation, assessment parsing, topic
  selection, field/provenance application and digest publication. Public signatures, prompt
  strings, keys, limits, SQL and journal operations remain unchanged.
- `src/app/core/daily/provider_requests.py`: extract the Jev topic threshold; name the code doc
  in the module docstring.
- `src/app/core/daily/enrichment.md`: register provider requests in `covers`, link characterization
  tests and describe the helper flow; no behavior or policy change.
- `tests/unit/test_daily_enrichment.py`: characterize review parsing, source/admission precedence,
  acquisition selection, summary limits and fallback errors.
- `tests/unit/test_daily_publish_day.py`: characterize reuse, preserved digests, billed journal
  rows, scope changes, reservation visibility, request fields and summary holds.
- `tests/unit/test_provider_requests.py`: freeze request versions/keys, byte bounds and exact
  reservation pricing.
- `tests/unit/test_provider_requests_parse.py`: characterize the exact topic confidence boundary
  and validation order.
- `docs/troubleshooting.md`: record the observed LCOV/mutator multiline-site mismatch and targeted
  forced-site workaround.

Decision (agent): keep the existing public entrypoints and extract private helpers within the
two modules. Source: the supplied prompt requires behavior preservation and small helpers.
Decision (agent): add provider requests to the existing doc's coverage list. Source: the supplied
prompt explicitly identifies it as covered, while the original header omitted it.

## Characterization tests

The original feature set passed 121 tests. The first 52 added cases passed against the unchanged
implementation before extraction. The feature set passed 185 tests after extraction, then 206
after mutation-driven strengthening (85 new cases, 31 new test functions). Test setup mistakes
(a missing row URL and the journal's committed-column
name) were corrected without changing production behavior.

| New test | Branch or invariant |
| --- | --- |
| `test_reusable_rejects_invalid_proof` | Wrong rubric, semantic flag and malformed/missing summary |
| `test_reusable_rejects_malformed_provenance` | Invalid JSON, null and list provenance return false |
| `test_reusable_summary_boundaries` | Fact count, empty text, word and character boundaries |
| `test_reusable_rejects_mismatched_applied_summary` | Category, applied text, literal quote and hash mismatches |
| `test_parse_review_flags_and_reason` | Boolean combinations, version alias and reason truncation/types |
| `test_parse_review_rejects_invalid_schema` | Non-object, missing or non-boolean flags |
| `test_parse_review_checks_model_before_choices_and_finish_before_json` | First failing envelope guard |
| `test_invalid_provider_answers_preserve_digest_and_billed_journal` | Invalid assessment/model/review preserves digest and priced response rows |
| `test_non_kept_assessment_holds_without_summary_calls` | Non-kept assessment makes no summary request |
| `test_enrich_fallback_bound_is_held_but_other_value_errors_propagate` | Bound error becomes hold; unrelated value error propagates |
| `test_long_grounded_summary_is_held_before_semantic_review` | Overlong grounded output is held without a review call |
| `test_publish_day_scope_change_preserves_previous_digest` | Changed scope fails before backup or replacement |
| `test_publish_day_dispatch_sees_committed_reservation` | Every dispatch observes a committed inflight reservation |
| `test_grounded_summary_accepts_exact_length_limits` | Exact word/character limits publish and remain reusable |
| `test_malformed_summary_records_exception_class` | Missing keys and null output retain exception-class details |
| `test_parse_topic_model_and_finish_guards` | Model and truncation checks precede payload access |
| `test_parse_topic_invalid_confidence_keeps_topic_without_score` | Invalid confidence retains a valid topic with null score |
| `test_jev_topic_boundary_and_unresolved_comparison` | Exact confidence threshold and unknown-comparison boundary review |
| `test_jev_choice_validation_precedes_probability_and_cleanup` | Unknown choice is reported before confidence and cleanup errors |
| `test_source_row_aware_stored_date_keeps_its_offset` | An aware stored timestamp keeps its offset when compared in UTC |
| `test_admission_from_proof_rejects_wrong_rubric_or_source` | Either proof mismatch refuses admission reuse |
| `test_publish_day_acquires_only_pending_sources` | Reused/admitted rows do not trigger downloads; final counts remain exact |
| `test_day_articles_end_is_exclusive_and_undated_rows_use_publication_day` | Midnight upper bound, undated matching day and dated-row precedence |
| `test_publish_day_preserves_request_fields_and_comparison_provenance` | Transport retries, provider fields, comparison flag/products, completion flags and nested private directories |
| `test_salvage_accepts_exact_length_limits` | Fact salvage accepts both exact length boundaries and labels model review correctly |
| `test_publish_day_preserves_pause_reason` | Supplied and default pause reasons, with no journal |
| `test_summary_request_schema_and_key_versions` | Default/recovery/quote-repair schemas, deterministic settings and exact versioned keys |
| `test_jev_request_byte_bound_includes_allowance_and_accepts_exact_limit` | Byte allowance, exact Jev bound and pre-dispatch oversized refusal |
| `test_deepseek_reservation_exact_byte_bound_and_pricing` | Exact byte bound and microdollar pricing for both allowed caps |
| `test_deepseek_reservation_rejects_unapproved_output_cap_with_small_input` | An output-cap violation alone refuses reservation |
| `test_summary_length_review_starts_after_eighty_words` | The exact word boundary does not request length review |

Strengthened existing tests also assert no page-cache access at the admitted-content minimum,
JSON-decode recovery error classification, partial-review provenance flags and fallback temperature.

## CRAP

Baseline values for the seven targets are those supplied in the task. The other three functions
at or above 8 are unchanged, with unchanged line coverage. No function in either file is at 10
or above. All after-values below use the final tool's full-suite coverage pass.

| Function | Before CRAP | After CC | After coverage | After CRAP |
| --- | ---: | ---: | ---: | ---: |
| `enrich` | 19.3 | 9 | 90.0% | 9.1 |
| `reusable` | 15.0 | 9 | 100% | 9.0 |
| `grounded_summary` | 14.4 | 7 | 100% | 7.0 |
| `publish_day` | 11.2 | 7 | 100% | 7.0 |
| `source_row` | 11.0 | 8 | 100% | 8.0 |
| `parse_review` | 10.4 | 6 | 100% | 6.0 |
| `parse_jev` | 11.0 | 9 | 100% | 9.0 |
| `admission_from_proof` | 9.0 | 9 | 100% | 9.0 |
| `_verified_products` | 9.0 | 9 | 100% | 9.0 |
| `salvage_supported_facts` | 8.0 | 8 | 100% | 8.0 |

## Final checks

Run in the requested order; after fixes, rerun only the failed target.

| Check | Last output / result | Exit |
| --- | --- | ---: |
| Full suite, `-n auto` | `2224 passed, 2 skipped, 8 warnings in 86.48s (0:01:26)` | 0 |
| `make lint` | `make: *** [lint-pylint] Error 24` | 2 |
| Pylint diagnostic | Two new helper signatures and test-module length | 2 |
| Pylint after fix | `Your code has been rated at 10.00/10` | 0 |
| Crapper | Full coverage suite: `2224 passed, 2 skipped, 1 warning in 184.62s`; `.metrics/crap.edn` written | 0 |
| Dryer, threshold 0.8 | `No duplicate candidates found.` No pairs in either module or `jev.py`. | 0 |
| Full suite after the last added test, `-n auto` | `2245 passed, 2 skipped, 8 warnings in 110.57s (0:01:50)` | 0 |
| Final `make lint` after test strengthening | `Your code has been rated at 10.00/10`; Ruff, mypy and Pylint pass | 0 |
| Standalone code-doc checker, last | `code docs: 15 checked, ok`, `exit=0` | 0 |

Ruff and mypy passed in the initial make lint run. The Pylint fix made helper arguments
keyword-only and moved publication tests into the existing publish-day test module. The crapper
coverage run validated the complete suite after that move.

Two PostgreSQL integration tests skip because `AINEWS_TEST_POSTGRES_URL` is unset. No database
service was started. Independent doc review is left to the separate reviewer required by the task.

## Mutation results

Initial full inventories ran once each, one file at a time, with the requested four feature files,
existing full-suite coverage and bytecode writes disabled. Follow-ups reran only failed sites,
plus the five omitted sites forced with `--no-coverage --lines ...`; already killed sites were
carried forward. No production code changed to satisfy mutations.

| File / run | Sites | Killed | Survived | Uncovered | Exit |
| --- | ---: | ---: | ---: | ---: | ---: |
| `enrichment.py`, initial | 154 | 132 | 19 | 3 | 3 |
| `provider_requests.py`, initial | 72 | 57 | 13 | 2 | 3 |
| `enrichment.py`, targeted follow-up | 154 | 153 | 1 | 0 | 3 |
| `provider_requests.py`, targeted follow-up | 72 | 72 | 0 | 0 | 0 |

Every initial enrichment survivor, using unchanged source line numbers:

| Line / mutation | Resolution |
| --- | --- |
| 65 `<` to `<=` | Killed by exact next-midnight exclusion in the day-scope test. |
| 66 `==` to `!=` | Killed by matching/nonmatching undated publication-day rows. |
| 115 `or` to `and` | Killed by the aware stored-date offset test. |
| 133 `>=` to `>` | Killed by asserting no cache access for admitted content at the minimum. |
| 161 `or` to `and` | Killed by refusal of a wrong rubric with a matching source hash. |
| 227 `True` to `False` | Killed by the persisted model-review provenance flag. |
| 229 `and` to `or` | Killed by asserting JSONDecodeError recovery classification. |
| 246 word limit `<=` to `<` | Killed by salvage at the exact word boundary. |
| 246 character limit `<=` to `<` | Killed by salvage at the exact character boundary. |
| 251 `True` to `False` | Killed by the partial-review provenance flag. |
| 261 message index 0 to 1 | Killed by decoding and comparing the summary's user payload. |
| 374 `==` to `!=` | Killed by both comparison flags and persisted product names. |
| 476 retries 0 to 1 | Killed by asserting the actual transport construction has retries=0. |
| 525 parents True to False | Killed by publishing into missing nested parent directories. |
| 528 parents True to False | Equivalent: the immediately preceding root mkdir/chmod guarantees this direct parent exists. Retained. |
| 533 `or` to `and` | Killed by supplied and default collection-pause reasons. |
| 549 deleted `not` | Killed by asserting only the pending article is acquired. |
| 549 `and` to `or` | Killed by excluding reused and admitted rows from acquisition. |
| 550 `or` to `and` | Killed by recognizing admitted nonempty source content without another download. |

Every initial provider-request survivor, using unchanged source line numbers:

| Line / mutation | Resolution |
| --- | --- |
| 125 default False to True | Killed by asserting the default request omits quote repair. |
| 127 `!=` to `==` | Killed by exact default/recovery schema selection. |
| 138 temperature 0 to 1 | Killed by request-field assertions. |
| 148 temperature 0 to 1 | Killed by fallback request-field assertions. |
| 163 `==` to `!=` | Killed by exact default/recovery request-key fingerprints. |
| 165 message index 0 to 1 | Killed by the quote-repair versioned request key. |
| 175 `+` to `-` | Killed by the Jev allowance and overflow boundary test. |
| 175 `<=` to `<` | Killed by the accepted exact Jev byte bound. |
| 186 `>` to `>=` | Killed by the accepted exact DeepSeek byte bound. |
| 186 `or` to `and` | Killed by independent input-bound and output-cap violations. |
| 188 `*` to `/` | Killed by exact input-reservation pricing. |
| 189 `*` to `/` | Killed by exact output-reservation pricing for both approved caps. |
| 302 `>` to `>=` | Killed by the exact summary-word boundary's false review flag. |

The five initially uncovered tokens are in multiline bodies/calls whose individual lines LCOV did
not mark. All five were killed by forced targeted execution, checking review
temperature and publication completion flags (enrichment lines 200, 520), admission-question setup
and the exact comparison threshold (provider-request lines 114, 217).

Totals after targeted follow-ups: 226 sites, 225 killed, one documented equivalent survivor and
zero uncovered. Enrichment's exit remains 3 solely because the tool retains the equivalent site;
provider requests exits 0. Logs are in `.metrics/*mutator*.log` and per-function records in
`.metrics/mutate/`. Crapper was not repeated: only tests/docs changed after its successful pass.

## Handoff

Prompts for another session must be saved before sharing: feature prompts belong in
`specs/<NNN>-<name>/records/`; other prompts and open reports belong in `docs/work/`, then
`docs/archive/<YYYY-MM>/` when finished. Never overwrite an earlier prompt.
