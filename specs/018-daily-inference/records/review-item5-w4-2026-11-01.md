# Review: PR #166 (W4 collect job) and commit ef286a1 on PR #164 (2026-11-01)

Reviewer: background agent (Sonnet), prompt `prompt-item5-w4-review-2026-11-01.md`, read-only.
Saved by the coordinator from the agent's final message.

## (a) ef286a1 on #164: merge

All six first-review items fixed; relative-import scan and core-never-imports-storage tests checked
by mutation; new cut/batch/boundary/empty tests real; single writer and manual PostgreSQL check in
the doc. Nice to have: one over-long line in the `world.md` prune rule.

## (b) #166: merge after fixes

### Must fix

1. Deploy breaks on sudoers. `scripts/install_daily_timers.sh:69-103` installs the world service and
   timer and runs `sudo -n systemctl enable --now ai-news-daily-world.timer` under `set -eu`;
   `deploy_prod.sh:311` runs it on every deploy. Server `/etc/sudoers.d/ai-news-deploy` allows exact
   arguments only, without the world files. `docs/deploy.md:100-106` still says "six unit files".
   **Coordinator verified on prod (read-only, 2026-11-01): the sudoers file has only the six
   fetch/digest/archive installs and the listed systemctl calls; no world entries.**

### Should fix

2. A missed night loses the day: `yesterday_utc` with `Persistent=false`; plan 6.1 asks for catch-up.
   Fix: after D-1 also run D-2 (no download if complete; 12-in-a-row stop bounds retries).

### Nice to have

3. Prune in collect is untested (removing `repo.prune()` keeps all 10 collect tests green).
4. `.env` parsing in `run_daily_world_job.sh:10-22` fails safe but treats CRLF, trailing comment or
   space, `export X=`, spaces around `=` as off; quoted values and last-wins untested; `1/yes/on`
   accepted but undocumented.
5. `skipped` undercounted after the 12-missing stop (`world_collect.py:91-93`).
6. `partial` is not stored; W5/W6 will need it (derivable from `done_files`); note in doc.
7. `docs/deploy.md` repeats "more than 8 of 192"; name the constant.

### Fine

Skip of done files before download; commit per file (`test_collect_crash_keeps_finished_files`);
partial at 8 and 9; summary fields; streaming invariant holds; switch off = no lock, container or
download; CLI ignores the switch; job script same shape as archive (lock, release image, timeout,
exit 0); 3300 + 1800 + 300 = 5400 s unit limit; `gdelt.py` refactor keeps W2 behavior; doc matches
except prune. W5 should recheck timing against a 05:00 bulletin job.

## Checks run

Scoped pytest 96 passed; ruff ok; `bash -n` ok; code docs ok; two mutations (prune: not caught;
relative import: caught); dryer none; crapper none >= 10. Not run: full pytest, `make lint`,
PostgreSQL, GDELT.
