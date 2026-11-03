Completed: every function in both modules is below CRAP 10.

Files changed:

- [enrichment.py](src/app/core/daily/enrichment.py): extracted small helpers; preserved public signatures and behavior.
- [provider_requests.py](src/app/core/daily/provider_requests.py): extracted Jev topic selection.
- [enrichment.md](src/app/core/daily/enrichment.md): updated helper map, test references and provider-request coverage.
- [test_daily_enrichment.py](tests/unit/test_daily_enrichment.py): source, admission, recovery and acquisition branches.
- [test_daily_publish_day.py](tests/unit/test_daily_publish_day.py): reuse, journal state/order, requests, scope and salvage boundaries.
- [test_provider_requests.py](tests/unit/test_provider_requests.py): versions, keys, byte bounds and pricing.
- [test_provider_requests_parse.py](tests/unit/test_provider_requests_parse.py): confidence and word thresholds.
- [troubleshooting.md](docs/troubleshooting.md): documented LCOV’s omitted multiline sites.
- [Validation report](docs/work/report-ub-enrichment-2026-11-03.md): all 31 new tests/85 cases, branch mappings and individual survivor resolutions.

| Function | CRAP before → after |
|---|---:|
| `enrich` | 19.3 → 9.1 |
| `reusable` | 15.0 → 9.0 |
| `grounded_summary` | 14.4 → 7.0 |
| `publish_day` | 11.2 → 7.0 |
| `source_row` | 11.0 → 8.0 |
| `parse_review` | 10.4 → 6.0 |
| `parse_jev` | 11.0 → 9.0 |
| `admission_from_proof` | 9.0 → 9.0 |
| `_verified_products` | 9.0 → 9.0 |
| `salvage_supported_facts` | 8.0 → 8.0 |

Final checks:

- Full suite after the last added test: **2245 passed, 2 skipped**, exit **0**.
- `make lint`: **10.00/10**, exit **0**.
- Crapper: exit **0**.
- Dryer: **no duplicate candidates**, exit **0**.
- Doc checker, last: **15 checked, ok**, exit **0**.

| Mutation result | Sites | Killed | Survived | Uncovered | Exit |
|---|---:|---:|---:|---:|---:|
| Enrichment | 154 | 153 | 1 | 0 | 3 |
| Provider requests | 72 | 72 | 0 | 0 | 0 |

The retained survivor is equivalent: the day directory’s parent already exists after root creation. All other survivors were killed by stronger tests.

Skipped: two PostgreSQL tests require `AINEWS_TEST_POSTGRES_URL`. No network, paid calls, sub-agents, commits, pushes or `gh` commands were used.