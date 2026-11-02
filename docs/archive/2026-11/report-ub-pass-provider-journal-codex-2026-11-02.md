Completed the refactor. Every function has complexity and CRAP below 10; both maxima are 8. Public signatures, SQL, guards, costs, exceptions and payment ordering remain unchanged.

Files changed:

- [provider_journal.py](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/ub-provider-journal/src/app/storage/provider_journal.py): extracted review, replay, dispatch, receipt, validation and reporting helpers.
- [provider_journal.md](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/ub-provider-journal/src/app/storage/provider_journal.md): added behavior, flow diagram, invariants, decisions and test mapping.
- [test_provider_journal.py](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/ub-provider-journal/tests/unit/test_provider_journal.py): added 25 tests comprising 88 cases.
- [README.md](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/ub-provider-journal/README.md): registered the feature doc.
- [docs/README.md](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/ub-provider-journal/docs/README.md): registered the feature doc.
- [src/app/README.md](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/ub-provider-journal/src/app/README.md): registered the feature doc.
- [troubleshooting.md](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/ub-provider-journal/docs/troubleshooting.md): recorded the pytest-cov module-preimport failure and filesystem-source workaround.

The first 84 characterization cases passed before refactoring. Four further cases addressed mutation survivors.

| New test | Branch or guarantee covered |
| --- | --- |
| `test_journal_configuration_guards` | Missing caps, excessive provider caps, empty retry delays |
| `test_transport_review_requires_reason` | Invalid or blank review reasons |
| `test_transport_review_eligibility` | Every accepted transport class; retained cost and provenance |
| `test_transport_review_refuses_nontransport_or_received_rows` | Missing row, wrong state/error, existing usage/response |
| `test_transport_review_rolls_back` | Transaction failure leaves no partial review |
| `test_review_failed_transports_counts_only_eligible_rows` | Disabled review, eligible count and repeated review |
| `test_attempt_chain_requires_review_provenance` | Missing reason/provenance and unsafe states |
| `test_attempt_reviews_old_transport_before_retry` | Review of a failure left by an earlier run |
| `test_unreviewable_http_error_stops_with_reservation` | HTTP error outside the review allowlist |
| `test_callback_stop_does_not_reserve_or_dispatch` | Callback rejection before reservation |
| `test_transport_attempt_chain_replays_and_exhausts` | Retry keys, delays, linkage, replay and dispatched flag |
| `test_reservation_guards_and_rollback` | Unsafe prior calls block reservations |
| `test_duplicate_reservation_and_link_failure_roll_back` | Duplicate key and failed attempt-link insertion |
| `test_caps_allow_exact_boundary` | Exact provider/total caps remain allowed |
| `test_total_cap_blocks_even_when_provider_has_room` | Independent cumulative-cap arithmetic |
| `test_dispatch_and_receipt_order` | Durable reservation before POST; pricing before receipt commit |
| `test_custom_key_and_reservation_replay` | Custom functions and callback-free replay |
| `test_saved_response_guards` | Unknown usage and invalid saved body |
| `test_received_response_guards` | Success, malformed JSON/body, HTTP failure, missing/excessive/equal-bound usage |
| `test_transient_retry_order_and_release` | Retry sequence and deletion of unbilled call/link |
| `test_transient_release_guards` | Rows that must retain their reservation |
| `test_priced_usage_validation` | Token types, booleans, negatives, zero and rounding |
| `test_summary_restore_guards` | Missing receipt/usage, status/price mismatch and parser exceptions |
| `test_truncated_summary_review_guards` | Truncation status, model, usage and response checks |
| `test_report_filters_tokens_and_keeps_unknown_cost` | Token filtering and complete report totals |

Final check results:

| Check | Last result | Exit |
| --- | --- | --- |
| Full suite | `2092 passed, 2 skipped, 8 warnings in 42.06s` | 0 |
| `make lint` | `Your code has been rated at 10.00/10` | 0 after correcting test-style findings |
| Crapper | Report below; coverage suite: `2092 passed, 2 skipped, 1 warning` | 0 |
| Dryer, threshold 0.8 | `No duplicate candidates found.` — no pairs | 0 |
| Mutator, initial | 140 killed, 6 survived, 1 uncovered; 147 sites | 3 |
| Mutator, after added assertions | 145 killed, 1 survived, 1 uncovered; 99.3% | 3 |
| Strict code-doc check, last | `code docs: 15 checked, ok` / `exit=0` | 0 |

Crapper values are **CC / coverage % / CRAP**. Before values are those supplied in the prompt; all after values were measured.

| Function | Before | After |
| --- | --- | --- |
| `PilotJournal.call` | 21 / 90.9 / 21.3 | 8 / 100 / 8.0 |
| `PilotJournal._attempt` | 14 / 71.4 / 18.6 | 7 / 100 / 7.0 |
| `PilotJournal.review_transport_failure` | 8 / 50 / 16.0 | 5 / 100 / 5.0 |
| `PilotJournal.restore_valid_summary` | 7 / 50 / 13.1 | 3 / 100 / 3.0 |
| `priced_usage` | — | 8 / 100 / 8.0 |
| `_json_or_none` | — | 2 / 100 / 2.0 |
| `_reviewable_transport` | — | 4 / 100 / 4.0 |
| `_is_priced_truncation` | — | 6 / 100 / 6.0 |
| `_report_tokens` | — | 8 / 100 / 8.0 |
| `TransportAttemptsExhausted.__init__` | — | 1 / 100 / 1.0 |
| `PilotJournal.__init__` | — | 7 / 100 / 7.0 |
| `PilotJournal.close` | — | 1 / 100 / 1.0 |
| `PilotJournal.reserve` | — | 7 / 100 / 7.0 |
| `PilotJournal.fail` | — | 1 / 100 / 1.0 |
| `PilotJournal.review_failed_transports` | — | 2 / 100 / 2.0 |
| `PilotJournal._require_transport_review` | — | 8 / 100 / 8.0 |
| `PilotJournal._release_unbilled_transient` | — | 6 / 100 / 6.0 |
| `PilotJournal.has_response` | — | 1 / 100 / 1.0 |
| `PilotJournal.review_truncated_summaries` | — | 5 / 100 / 5.0 |
| `PilotJournal._restorable_summary` | — | 6 / 100 / 6.0 |
| `PilotJournal._retry_after_failure` | — | 2 / 100 / 2.0 |
| `PilotJournal._replay_response` | — | 6 / 100 / 6.0 |
| `PilotJournal._post_with_transient_retries` | — | 4 / 75 / 4.2 |
| `PilotJournal._record_response` | — | 2 / 100 / 2.0 |
| `PilotJournal._validate_response` | — | 5 / 100 / 5.0 |
| `PilotJournal.committed_usd` | — | 1 / 100 / 1.0 |
| `PilotJournal.report` | — | 4 / 100 / 4.0 |

Mutation disposition:

- Three budget mutations at line 146, the missing-usage guard mutation at line 277, and the equality-bound mutation at line 352 are now killed by added assertions.
- **Equivalent survivor, line 212, `1 → 0`:** changes a copied response slot that is subsequently discarded; only the tuple’s state is read.
- **Uncovered site, line 91, `0 → 1`:** LCOV does not mark the continued default-argument line executed; the `(0,)` default is explicitly asserted.

The doc contains one agent decision:

> decided 2026-11-02 (agent): extract private helpers around existing decisions to keep payment ordering visible while preserving guards, SQL, keys, exceptions and return values.

Two PostgreSQL integration tests were skipped because `AINEWS_TEST_POSTGRES_URL` was unset. Per the speed rule, full-suite/lint checks were not repeated after the four mutation-driven test cases; the mutator’s passing baseline validated those additions. The strict checker’s diff mode compares committed history.

No network, paid calls, sub-agents, commits, pushes or `gh` commands were used.