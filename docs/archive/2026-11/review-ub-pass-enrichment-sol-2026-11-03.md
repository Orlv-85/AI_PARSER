No must-fix findings. The refactor preserves results, exceptions/messages, short-circuiting, request bodies/keys, journal ordering, caps and SQL. Doc coverage and named tests check out.

Hand mutations assessed **statically**:

| Mutation | Expected detecting test |
|---|---|
| Bypass summary reuse | `test_publish_day_all_reused_writes_no_progress_json` |
| Validate admission probability before choice | `test_jev_choice_validation_precedes_probability_and_cleanup` |
| Remove output-cap check | `test_deepseek_reservation_rejects_unapproved_output_cap_with_small_input` |
| Omit provider from cache key | `test_summary_request_schema_and_key_versions` |
| Accept topic confidence 0.699 | `test_jev_topic_boundary_and_unresolved_comparison` |

Survivor: swapping `_provider_keys` guards appears undetected when admission is disabled **and** a key is missing; existing cases test each failure separately. This is a nonblocking coverage gap. The executor’s directory-parent mutant is equivalent.

Validation: **77 tests passed** using in-memory capture; code-doc checker: **15 checked, OK**. The requested complete scoped run failed before collection because the read-only sandbox prevented temporary-file creation. No files changed.

clean