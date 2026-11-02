Implemented `bulletin daily`, the disabled-by-default job, 04:30 UTC timer, and both switches.

Files changed, one line each:

- [daily.py](src/app/core/bulletin/daily.py): shared assessment, build, writer and storage orchestration.
- [main.py](src/app/cli/main.py): daily command and shared validation.
- [settings.py](src/app/config/settings.py): both switches default off.
- [run_daily_bulletin_job.sh](scripts/run_daily_bulletin_job.sh): switch, release image, lock and timeout.
- [install_daily_timers.sh](scripts/install_daily_timers.sh): bulletin service and timer.
- [ai-news-deploy](deploy/sudoers.d/ai-news-deploy): required installer permissions.
- [test_bulletin_daily.py](tests/unit/test_bulletin_daily.py): daily command and helper tests with fake providers.
- [test_daily_timers.py](tests/unit/test_daily_timers.py): schedule and timeout budget tests.
- [test_deepseek_digest.py](tests/unit/test_deepseek_digest.py): bulletin script tests using stubs.
- [daily.md](src/app/core/bulletin/daily.md): behavior, decisions and test mapping.
- [builder.md](src/app/core/bulletin/builder.md): daily job reference.
- [writer.md](src/app/core/bulletin/writer.md): daily job reference.
- [world_change.md](src/app/core/bulletin/world_change.md): daily assessment reference.
- [configuration.md](docs/configuration.md): three environment switches.
- [troubleshooting.md](docs/troubleshooting.md): structured logging case.
- [README.md](README.md): doc registration.
- [docs/README.md](docs/README.md): doc registration.
- [src/app/README.md](src/app/README.md): doc registration.

The initial TDD run failed as expected: `26 failed, 76 deselected, 1 warning in 3.82s`, exit **1**, because the command, settings, script and timer were absent.

| Final check | Output/result | Exit |
|---|---|---:|
| Initial parallel full suite | 2 failed, 1978 passed, 2 skipped; doc and sudoers failures fixed, both reruns passed | 1 → 0 |
| Final full suite through crapper coverage | `1981 passed, 2 skipped, 1 warning` | 0 |
| `make lint` | `Your code has been rated at 10.00/10` | 0 |
| Shell syntax | No output | 0 |
| Crapper | Wrote `.metrics/crap.edn`; no bulletin/daily function has CRAP ≥10; highest is `bulletin_build`, **9** | 0 |
| Dryer | `No duplicate candidates found.` | 0 |
| Mutator | **12 sites, 12 killed, 0 survived, 0 uncovered** | 0 |
| Strict docs, last command | `code docs: 14 checked, ok` | 0 |

Mutation initially found **8 killed, 3 survived, 1 uncovered**, exit **3**. Added dry-run and missing-digest count assertions to kill the survivors; reran with `--no-coverage` to exercise the default-argument site initially marked uncovered.

Agent decisions: store missing digests as `no_digest`; log runtime faults as `daily_failed` with exit zero; use a 1800-second CLI limit and 7500-second service timeout. The existing deploy contract required the added sudoers entries.

Two PostgreSQL tests remain skipped because `AINEWS_TEST_POSTGRES_URL` is unset. Deployment requires root to apply the updated sudoers sample.

No network, paid calls, commits, pushes, `gh` commands or sub-agents used.