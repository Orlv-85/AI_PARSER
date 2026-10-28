# Report: restore check before the weekly v2 table drop (T041) (2026-10-28)

Coordinator, 2026-10-28 ~17:30 UTC. Read-only on prod.

- Dump: server copy `/opt/ai-news/backups/postgres_20261028T084143Z.sql.gz` (72.5 MB), copied to
  the coordinator's machine; sha256 `bef9cffe...9f72c42` equal on both sides.
- Restored into a throwaway `postgres:18-alpine` container with `psql -v ON_ERROR_STOP=1`: exit 0,
  no errors. Container and plaintext copy removed afterwards.
- Row counts, restored = prod (read-only SELECT on prod at the same time):

| Table | Rows |
| --- | --- |
| weekly_source_versions | 152 |
| weekly_coverage_attempts | 2846 |
| weekly_input_observations | 7139 |
| weekly_decisions | 0 |
| weekly_topic_versions | 0 |
| weekly_jobs | 2 |
| weekly_snapshots | 2 |
| weekly_publications | 4 |
| articles | 7331 |

- No fetch ran between the dump and the check (fetch is nightly), so this does not yet prove that
  R1 stopped the `weekly_*` writes; that is the 2026-10-29 check (counts unchanged after the night).
- Not checked: the encrypted off-site B2 copy (no B2 key on this machine); the server copy is the
  same nightly dump that is uploaded.
